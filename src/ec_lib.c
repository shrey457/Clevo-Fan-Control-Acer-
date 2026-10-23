#define _GNU_SOURCE
#include "ec_lib.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/io.h>
#include <sys/wait.h>
#include <unistd.h>

#define EC_SC 0x66
#define EC_DATA 0x62
#define IBF 1
#define OBF 0
#define EC_SC_READ_CMD 0x80

#define EC_REG_CPU_TEMP    0x07
#define EC_REG_GPU_TEMP    0xCD
#define EC_REG_FAN1_DUTY   0xCE
#define EC_REG_FAN2_DUTY   0xCF
#define EC_REG_FAN1_RPM_HI 0xD0
#define EC_REG_FAN1_RPM_LO 0xD1
#define EC_REG_FAN2_RPM_HI 0xD2
#define EC_REG_FAN2_RPM_LO 0xD3

static int ec_io_wait(unsigned short port, uint8_t flag, uint8_t value) {
    uint8_t data = inb(port);
    int i = 0;
    while ((((data >> flag) & 0x1) != value) && (i++ < 100)) {
        usleep(1000);
        data = inb(port);
    }
    return (i >= 100) ? -1 : 0;
}

static int ec_io_read(uint8_t reg) {
    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(EC_SC_READ_CMD, EC_SC);

    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(reg, EC_DATA);

    if (ec_io_wait(EC_SC, OBF, 1) != 0) return -1;
    return (int)inb(EC_DATA);
}

static int ec_io_do(uint8_t cmd, uint8_t reg, uint8_t value) {
    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(cmd, EC_SC);

    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(reg, EC_DATA);

    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(value, EC_DATA);

    return ec_io_wait(EC_SC, IBF, 0);
}

static int clamp_val(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static int calc_rpm(int hi, int lo) {
    if (hi < 0 || lo < 0) return 0;
    uint32_t raw = ((uint32_t)(uint8_t)hi << 8) | (uint32_t)(uint8_t)lo;
    return (raw > 0) ? (int)(2156220 / raw) : 0;
}

/* Safe execution of /usr/bin/nvidia-smi without invoking /bin/sh (avoids popen) */
static int run_nvidia_smi_temp(void) {
    if (access("/usr/bin/nvidia-smi", X_OK) != 0) return -1;

    int pipefd[2];
    if (pipe2(pipefd, O_CLOEXEC) != 0) return -1;

    pid_t pid = fork();
    if (pid < 0) {
        close(pipefd[0]);
        close(pipefd[1]);
        return -1;
    }

    if (pid == 0) {
        /* Child: redirect stdout to pipe and stderr to /dev/null */
        close(pipefd[0]);
        dup2(pipefd[1], STDOUT_FILENO);
        close(pipefd[1]);

        int devnull = open("/dev/null", O_WRONLY | O_CLOEXEC);
        if (devnull >= 0) {
            dup2(devnull, STDERR_FILENO);
            close(devnull);
        }

        char *const args[] = {
            "/usr/bin/nvidia-smi",
            "--query-gpu=temperature.gpu",
            "--format=csv,noheader,nounits",
            NULL
        };
        execv(args[0], args);
        _exit(127);
    }

    /* Parent */
    close(pipefd[1]);
    char buf[32] = {0};
    ssize_t n = read(pipefd[0], buf, sizeof(buf) - 1);
    close(pipefd[0]);

    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR) break;
    }

    if (n > 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0) {
        int t = atoi(buf);
        if (t > 0 && t < 125) return t;
    }
    return -1;
}

static int cpu_temp_sysfs(void) {
    /* 1. Try thermal zones */
    for (int z = 0; z < 8; z++) {
        char type_path[64], temp_path[64];
        snprintf(type_path, sizeof(type_path), "/sys/class/thermal/thermal_zone%d/type", z);
        int tfd = open(type_path, O_RDONLY | O_CLOEXEC);
        if (tfd >= 0) {
            char tbuf[64] = {0};
            ssize_t tn = read(tfd, tbuf, sizeof(tbuf) - 1);
            close(tfd);
            if (tn > 0 && (strstr(tbuf, "x86_pkg_temp") || strstr(tbuf, "TCPU") ||
                           strstr(tbuf, "cpu") || strstr(tbuf, "acpitz"))) {
                snprintf(temp_path, sizeof(temp_path), "/sys/class/thermal/thermal_zone%d/temp", z);
                int dfd = open(temp_path, O_RDONLY | O_CLOEXEC);
                if (dfd >= 0) {
                    char valbuf[32] = {0};
                    ssize_t vn = read(dfd, valbuf, sizeof(valbuf) - 1);
                    close(dfd);
                    if (vn > 0) {
                        int milli = atoi(valbuf);
                        int c = (milli > 1000) ? (milli / 1000) : milli;
                        if (c > 10 && c < 120) return c;
                    }
                }
            }
        }
    }

    /* 2. Try hwmon CPU drivers (coretemp, k10temp, zenpower) */
    DIR *d = opendir("/sys/class/hwmon");
    if (d) {
        int best = -1;
        int rootfd = dirfd(d);
        if (rootfd >= 0) {
            struct dirent *de;
            while ((de = readdir(d)) != NULL) {
                if (strncmp(de->d_name, "hwmon", 5) != 0) continue;
                int hwfd = openat(rootfd, de->d_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
                if (hwfd < 0) continue;
                int namefd = openat(hwfd, "name", O_RDONLY | O_CLOEXEC);
                if (namefd >= 0) {
                    char namebuf[64] = {0};
                    ssize_t n = read(namefd, namebuf, sizeof(namebuf) - 1);
                    close(namefd);
                    if (n > 0 && (strstr(namebuf, "coretemp") || strstr(namebuf, "k10temp") ||
                                  strstr(namebuf, "zenpower") || strstr(namebuf, "cpu"))) {
                        for (int i = 1; i <= 8; i++) {
                            char fn[32];
                            snprintf(fn, sizeof(fn), "temp%d_input", i);
                            int ifd = openat(hwfd, fn, O_RDONLY | O_CLOEXEC);
                            if (ifd >= 0) {
                                char buf[32] = {0};
                                ssize_t r = read(ifd, buf, sizeof(buf) - 1);
                                close(ifd);
                                if (r > 0) {
                                    int c = atoi(buf) / 1000;
                                    if (c > best && c < 120) best = c;
                                }
                            }
                        }
                    }
                }
                close(hwfd);
            }
        }
        closedir(d);
        if (best > 10 && best < 120) return best;
    }
    return -1;
}

int ec_lib_init(void) {
    if (ioperm(EC_DATA, 1, 1) != 0) return -1;
    if (ioperm(EC_SC,   1, 1) != 0) return -1;
    return 0;
}

int ec_lib_cpu_temp(void) {
    int t = ec_io_read(EC_REG_CPU_TEMP);
    if (t > 10 && t < 115) return t;
    /* Robust fallback to Linux sysfs thermal reading */
    int sf = cpu_temp_sysfs();
    if (sf > 0) return sf;
    return (t > 0 && t < 125) ? t : 0;
}

int ec_lib_gpu_temp(void) {
    /* 1. Try hwmon sysfs (nvidia, amdgpu, i915, xe) */
    DIR *d = opendir("/sys/class/hwmon");
    if (d) {
        int best = -1;
        int rootfd = dirfd(d);
        if (rootfd >= 0) {
            struct dirent *de;
            while ((de = readdir(d)) != NULL) {
                if (strncmp(de->d_name, "hwmon", 5) != 0) continue;
                int hwfd = openat(rootfd, de->d_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
                if (hwfd < 0) continue;
                int namefd = openat(hwfd, "name", O_RDONLY | O_CLOEXEC);
                if (namefd >= 0) {
                    char namebuf[64] = {0};
                    ssize_t n = read(namefd, namebuf, sizeof(namebuf) - 1);
                    close(namefd);
                    if (n > 0 && (strstr(namebuf, "nvidia") || strstr(namebuf, "amdgpu") ||
                                  strstr(namebuf, "i915")   || strstr(namebuf, "xe"))) {
                        for (int i = 1; i <= 8; i++) {
                            char fn[32];
                            snprintf(fn, sizeof(fn), "temp%d_input", i);
                            int tfd = openat(hwfd, fn, O_RDONLY | O_CLOEXEC);
                            if (tfd >= 0) {
                                char buf[32] = {0};
                                ssize_t r = read(tfd, buf, sizeof(buf) - 1);
                                close(tfd);
                                if (r > 0) {
                                    int c = atoi(buf) / 1000;
                                    if (c > best && c < 120) best = c;
                                }
                            }
                        }
                    }
                }
                close(hwfd);
            }
        }
        closedir(d);
        if (best > 0 && best < 120) return best;
    }

    /* 2. Direct NVIDIA utility via safe fork/execv (no shell/popen) */
    int nv = run_nvidia_smi_temp();
    if (nv > 0) return nv;

    /* 3. Fallback: EC register */
    int ec = ec_io_read(EC_REG_GPU_TEMP);
    return (ec > 0 && ec < 120) ? ec : 0;
}

int ec_lib_fan1_duty_read(void) {
    int raw = ec_io_read(EC_REG_FAN1_DUTY);
    if (raw < 0) return 0;
    int pct = (int)((raw / 255.0) * 100.0 + 0.5);
    return clamp_val(pct, 0, 100);
}

int ec_lib_fan2_duty_read(void) {
    int raw = ec_io_read(EC_REG_FAN2_DUTY);
    if (raw < 0) return 0;
    int pct = (int)((raw / 255.0) * 100.0 + 0.5);
    return clamp_val(pct, 0, 100);
}

int ec_lib_fan1_rpm_read(void) {
    int hi = ec_io_read(EC_REG_FAN1_RPM_HI);
    int lo = ec_io_read(EC_REG_FAN1_RPM_LO);
    return calc_rpm(hi, lo);
}

int ec_lib_fan2_rpm_read(void) {
    int hi = ec_io_read(EC_REG_FAN2_RPM_HI);
    int lo = ec_io_read(EC_REG_FAN2_RPM_LO);
    return calc_rpm(hi, lo);
}

int ec_lib_fan1_duty_write(int pct) {
    pct = clamp_val(pct, 0, 100);
    int v = (int)(pct / 100.0 * 255.0 + 0.5);
    return ec_io_do(0x99, 0x01, (uint8_t)v);
}

int ec_lib_fan2_duty_write(int pct) {
    pct = clamp_val(pct, 0, 100);
    int v = (int)(pct / 100.0 * 255.0 + 0.5);
    return ec_io_do(0x99, 0x02, (uint8_t)v);
}

int ec_lib_fan_set_both(int pct) {
    int r1 = ec_lib_fan1_duty_write(pct);
    int r2 = ec_lib_fan2_duty_write(pct);
    return (r1 == 0 && r2 == 0) ? 0 : -1;
}

int ec_lib_fan_reset(void) {
    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(0x99, EC_SC);
    if (ec_io_wait(EC_SC, IBF, 0) != 0) return -1;
    outb(0xFF, EC_DATA);
    return 0;
}
