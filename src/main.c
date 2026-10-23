/*
 * main.c
 *
 * Commands:
 *   set  <0..100>   - Set both fans to the same duty
 *   set1 <0..100>   - Set CPU (fan1/right) duty
 *   set2 <0..100>   - Set GPU (fan2/left) duty
 *   dump            - Show CPU/GPU temps and each fan's duty/RPM
 *   json            - Output fan & thermal status in JSON
 *   auto            - Auto mode: dynamic thermal curve with Zero-RPM support
 *   reset           - Restore fans to EC firmware auto control
 *
 * Security: Shell-free execution, capability-safe, O_CLOEXEC descriptors, input validation.
 */

#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/io.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* --- Program name --- */
#define NAME "fan-control"

/* --- EC I/O ports and commands --- */
#define EC_SC 0x66
#define EC_DATA 0x62
#define IBF 1
#define OBF 0
#define EC_SC_READ_CMD 0x80

/* --- Common EC register layout (typical Clevo/Uniwill) --- */
#define EC_REG_CPU_TEMP       0x07
#define EC_REG_GPU_TEMP       0xCD
#define EC_REG_FAN1_DUTY      0xCE
#define EC_REG_FAN2_DUTY      0xCF
#define EC_REG_FAN1_RPM_HI    0xD0
#define EC_REG_FAN1_RPM_LO    0xD1
#define EC_REG_FAN2_RPM_HI    0xD2
#define EC_REG_FAN2_RPM_LO    0xD3

/* --- Plausibility rules --- */
#define TEMP_MIN_VALID_C      10     /* below this we assume "sensor bad" */
#define TEMP_MAX_VALID_C      115    /* above this we assume "sensor bad" */
#define GPU_CPU_MAX_DIFF_C     45    /* GPU must be within +/-45°C of CPU to be trusted */

/* --- Prototypes --- */
static int     ec_init(void);
static int     ec_io_wait(unsigned short port, uint8_t flag, uint8_t value);
static int     ec_io_read(uint8_t reg);
static int     ec_io_do(uint8_t cmd, uint8_t reg, uint8_t value);

static int     is_temp_plausible(int t);
static int     sanitize_gpu_temp(int gpu_c, int cpu_c);

static int     cpu_temp(void);
static int     cpu_temp_sysfs(void);
static int     gpu_temp(void);
static int     gpu_temp_sysfs(void);
static int     gpu_temp_nvidia_smi(void);

static int     fan1_duty_read(void);
static int     fan2_duty_read(void);
static int     fan1_rpm_read(void);
static int     fan2_rpm_read(void);
static int     fan1_duty_write(int pct);
static int     fan2_duty_write(int pct);

static int     dump_status(void);
static int     dump_json(void);
static int     cmd_reset(void);
static int     cmd_set_both(int pct);
static int     cmd_set1(int pct);
static int     cmd_set2(int pct);
static int     cmd_auto(void);

static int     target_duty_from_avg_temp(int t_avg_c);
static int     step_from_avg_temp(int t_avg_c);
static int     clamp(int v, int lo, int hi);
static int     rpm_from_raw(int hi, int lo);
static int     parse_duty_arg(const char *str);

static volatile sig_atomic_t g_stop = 0;
static void on_sigint(int sig) { (void)sig; g_stop = 1; }

/* ------------------------- MAIN ------------------------- */

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr,
            "Usage: %s <command>\n"
            "Commands:\n"
            "  set   <0..100>  Set BOTH fans\n"
            "  set1  <0..100>  Set CPU fan (fan1)\n"
            "  set2  <0..100>  Set GPU fan (fan2)\n"
            "  dump            Show CPU/GPU temps and fan status\n"
            "  json            Output fan & thermal status in JSON\n"
            "  auto            Auto mode with dynamic curve & Zero-RPM\n"
            "  reset           Restore fans to EC firmware auto control\n",
            NAME);
        return EXIT_FAILURE;
    }

    if (ec_init() != 0) {
        fprintf(stderr, "EC init failed: %s (requires root or cap_sys_rawio)\n", strerror(errno));
        return EXIT_FAILURE;
    }

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = on_sigint;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    if (strcmp(argv[1], "dump") == 0) {
        return dump_status();
    }

    if (strcmp(argv[1], "json") == 0) {
        return dump_json();
    }

    if (strcmp(argv[1], "reset") == 0) {
        return cmd_reset();
    }

    if (strcmp(argv[1], "set") == 0) {
        if (argc < 3) { fprintf(stderr, "Usage: %s set <0..100>\n", NAME); return EXIT_FAILURE; }
        int pct = parse_duty_arg(argv[2]);
        if (pct < 0) {
            fprintf(stderr, "Error: Duty must be an integer between 0 and 100\n");
            return EXIT_FAILURE;
        }
        return cmd_set_both(pct);
    }

    if (strcmp(argv[1], "set1") == 0) {
        if (argc < 3) { fprintf(stderr, "Usage: %s set1 <0..100>\n", NAME); return EXIT_FAILURE; }
        int pct = parse_duty_arg(argv[2]);
        if (pct < 0) {
            fprintf(stderr, "Error: Duty must be an integer between 0 and 100\n");
            return EXIT_FAILURE;
        }
        return cmd_set1(pct);
    }

    if (strcmp(argv[1], "set2") == 0) {
        if (argc < 3) { fprintf(stderr, "Usage: %s set2 <0..100>\n", NAME); return EXIT_FAILURE; }
        int pct = parse_duty_arg(argv[2]);
        if (pct < 0) {
            fprintf(stderr, "Error: Duty must be an integer between 0 and 100\n");
            return EXIT_FAILURE;
        }
        return cmd_set2(pct);
    }

    if (strcmp(argv[1], "auto") == 0) {
        return cmd_auto();
    }

    fprintf(stderr, "Unknown command: %s\n", argv[1]);
    return EXIT_FAILURE;
}

/* ---------------------- Commands ------------------------ */

static int dump_status(void) {
    int tc = cpu_temp();
    int tg_raw = gpu_temp();
    int tg = sanitize_gpu_temp(tg_raw, tc);

    int d1 = fan1_duty_read();
    int r1 = fan1_rpm_read();

    int d2 = fan2_duty_read();
    int r2 = fan2_rpm_read();

    if (!is_temp_plausible(tc)) {
        printf("CPU: %d°C (INVALID) - Fan: %d%% %dRPM\n", tc, d1, r1);
    } else {
        printf("CPU: %d°C - Fan: %d%% %dRPM\n", tc, d1, r1);
    }

    if (tg >= 0) {
        printf("GPU: %d°C - Fan: %d%% %dRPM\n", tg, d2, r2);
    } else {
        printf("GPU: ignored (%d°C raw) - Fan: %d%% %dRPM\n", tg_raw, d2, r2);
    }
    return 0;
}

static int dump_json(void) {
    int tc = cpu_temp();
    int tg_raw = gpu_temp();
    int tg = sanitize_gpu_temp(tg_raw, tc);

    int d1 = fan1_duty_read();
    int r1 = fan1_rpm_read();

    int d2 = fan2_duty_read();
    int r2 = fan2_rpm_read();

    printf("{\"cpu\":%d,\"cpu_valid\":%s,\"gpu\":%d,\"gpu_raw\":%d,\"fan1_duty\":%d,\"fan1_rpm\":%d,\"fan2_duty\":%d,\"fan2_rpm\":%d}\n",
           tc, is_temp_plausible(tc) ? "true" : "false",
           tg, tg_raw,
           d1, r1,
           d2, r2);
    return 0;
}

static int cmd_reset(void) {
    if (ec_io_wait(EC_SC, IBF, 0) != 0) {
        fprintf(stderr, "Failed waiting for EC command port\n");
        return EXIT_FAILURE;
    }
    outb(0x99, EC_SC);
    if (ec_io_wait(EC_SC, IBF, 0) != 0) {
        fprintf(stderr, "Failed waiting for EC command port\n");
        return EXIT_FAILURE;
    }
    outb(0xFF, EC_DATA);
    printf("Fans restored to EC firmware auto control.\n");
    return 0;
}

static int cmd_set_both(int pct) {
    pct = clamp(pct, 0, 100);
    if (fan1_duty_write(pct) != 0) { fprintf(stderr, "Failed to set fan1\n"); return EXIT_FAILURE; }
    if (fan2_duty_write(pct) != 0) { fprintf(stderr, "Failed to set fan2\n"); return EXIT_FAILURE; }
    usleep(500 * 1000);
    return dump_status();
}

static int cmd_set1(int pct) {
    pct = clamp(pct, 0, 100);
    if (fan1_duty_write(pct) != 0) { fprintf(stderr, "Failed to set fan1\n"); return EXIT_FAILURE; }
    usleep(500 * 1000);
    return dump_status();
}

static int cmd_set2(int pct) {
    pct = clamp(pct, 0, 100);
    if (fan2_duty_write(pct) != 0) { fprintf(stderr, "Failed to set fan2\n"); return EXIT_FAILURE; }
    usleep(500 * 1000);
    return dump_status();
}

static int target_duty_from_avg_temp(int temp_c) {
    /* Dynamic thermal points allowing 0% silent Zero-RPM below 50°C */
    const struct { int t; int p; } points[] = {
        {50, 0},
        {58, 20},
        {66, 40},
        {74, 60},
        {82, 80},
        {88, 100}
    };
    const int n = (int)(sizeof(points) / sizeof(points[0]));

    if (temp_c <= points[0].t)
        return points[0].p;
    if (temp_c >= points[n - 1].t)
        return points[n - 1].p;

    /* Linear interpolation */
    for (int i = 0; i < n - 1; i++) {
        int t1 = points[i].t, p1 = points[i].p;
        int t2 = points[i + 1].t, p2 = points[i + 1].p;
        if (temp_c >= t1 && temp_c < t2) {
            double fraction = (double)(temp_c - t1) / (double)(t2 - t1);
            double percentage = p1 + (p2 - p1) * fraction;
            return (int)(percentage + 0.5);
        }
    }

    return 100;
}

static int step_from_avg_temp(int t_avg_c) {
    if (t_avg_c < 68) return 1;
    if (t_avg_c < 78) return 2;
    return 4;
}

static int cmd_auto(void) {
    int ring[3] = { -1, -1, -1 };
    int idx = 0, filled = 0;

    int current = 0;
    fan1_duty_write(current);
    fan2_duty_write(current);

    printf("Auto mode running (Ctrl+C to stop)...\n");

    while (!g_stop) {
        int tc = cpu_temp();
        int tg_raw = gpu_temp();

        /* Safety: if CPU temp implausible, run 100% full fan */
        if (!is_temp_plausible(tc)) {
            if (current != 100) {
                fan1_duty_write(100);
                fan2_duty_write(100);
                current = 100;
            }

            int r1s = fan1_rpm_read();
            int r2s = fan2_rpm_read();
            printf("CPU=%d°C (INVALID)  GPU=%d°C  -> Duty=100%%  (F1=%d RPM, F2=%d RPM)    \r",
                   tc, tg_raw, r1s, r2s);
            fflush(stdout);
            usleep(1000 * 1000);
            continue;
        }

        int tg = sanitize_gpu_temp(tg_raw, tc);
        int th = (tg >= 0) ? ((tc > tg) ? tc : tg) : tc;

        ring[idx] = th;
        idx = (idx + 1) % 3;
        if (filled < 3) filled++;

        int sum = 0;
        for (int i = 0; i < filled; i++) sum += ring[i];
        int t_avg = sum / filled;

        int step = step_from_avg_temp(t_avg);
        int target = target_duty_from_avg_temp(t_avg);

        /* Smooth hysteresis transition */
        int diff = target - current;
        int newduty = current;
        if (diff > 0) {
            newduty = (diff >= step) ? current + step : target;
        } else if (diff < 0) {
            newduty = current - 1;
        }
        newduty = clamp(newduty, 0, 100);

        if (newduty != current) {
            fan1_duty_write(newduty);
            fan2_duty_write(newduty);
            current = newduty;
        }

        int r1 = fan1_rpm_read();
        int r2 = fan2_rpm_read();

        if (tg >= 0) {
            printf("CPU=%d°C  GPU=%d°C  HOT=%d°C  AVG3=%d°C  TARGET=%d%%  -> Duty=%d%%  (F1=%d RPM, F2=%d RPM)    \r",
                   tc, tg, th, t_avg, target, current, r1, r2);
        } else {
            printf("CPU=%d°C  GPU=IGNORED(%d°C)  HOT=%d°C  AVG3=%d°C  TARGET=%d%%  -> Duty=%d%%  (F1=%d RPM, F2=%d RPM)    \r",
                   tc, tg_raw, th, t_avg, target, current, r1, r2);
        }
        fflush(stdout);

        usleep(1000 * 1000);
    }

    printf("\nAuto mode stopped. Restoring fans to EC firmware auto control...\n");
    cmd_reset();
    return 0;
}

static int is_temp_plausible(int t) {
    return (t >= TEMP_MIN_VALID_C && t <= TEMP_MAX_VALID_C);
}

static int sanitize_gpu_temp(int gpu_c, int cpu_c) {
    if (!is_temp_plausible(gpu_c)) return -1;
    if (is_temp_plausible(cpu_c)) {
        if (abs(gpu_c - cpu_c) > GPU_CPU_MAX_DIFF_C) return -1;
    }
    return gpu_c;
}

/* ---------------------- EC access ----------------------- */

static int ec_init(void) {
    if (ioperm(EC_DATA, 1, 1) != 0) return -1;
    if (ioperm(EC_SC,   1, 1) != 0) return -1;
    return 0;
}

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

/* ------------------- Sensing helpers -------------------- */

static int cpu_temp_sysfs(void) {
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

static int cpu_temp(void) {
    int t = ec_io_read(EC_REG_CPU_TEMP);
    if (t > 10 && t < 115) return t;
    int sf = cpu_temp_sysfs();
    if (sf > 0) return sf;
    return (t > 0 && t < 125) ? t : 0;
}

static int gpu_temp(void) {
    int t = gpu_temp_sysfs();
    if (t > 0) return t;
    t = gpu_temp_nvidia_smi();
    if (t > 0) return t;
    int ec = ec_io_read(EC_REG_GPU_TEMP);
    return (ec > 0 && ec < 120) ? ec : 0;
}

static int fan1_duty_read(void) {
    int raw = ec_io_read(EC_REG_FAN1_DUTY);
    if (raw < 0) return 0;
    int pct = (int)((raw / 255.0) * 100.0 + 0.5);
    return clamp(pct, 0, 100);
}

static int fan2_duty_read(void) {
    int raw = ec_io_read(EC_REG_FAN2_DUTY);
    if (raw < 0) return 0;
    int pct = (int)((raw / 255.0) * 100.0 + 0.5);
    return clamp(pct, 0, 100);
}

static int fan1_rpm_read(void) {
    int hi = ec_io_read(EC_REG_FAN1_RPM_HI);
    int lo = ec_io_read(EC_REG_FAN1_RPM_LO);
    return rpm_from_raw(hi, lo);
}

static int fan2_rpm_read(void) {
    int hi = ec_io_read(EC_REG_FAN2_RPM_HI);
    int lo = ec_io_read(EC_REG_FAN2_RPM_LO);
    return rpm_from_raw(hi, lo);
}

static int fan1_duty_write(int pct) {
    pct = clamp(pct, 0, 100);
    int v = (int)(pct / 100.0 * 255.0 + 0.5);
    return ec_io_do(0x99, 0x01, (uint8_t)v);
}

static int fan2_duty_write(int pct) {
    pct = clamp(pct, 0, 100);
    int v = (int)(pct / 100.0 * 255.0 + 0.5);
    return ec_io_do(0x99, 0x02, (uint8_t)v);
}

/* ----------------------- Utils -------------------------- */

static int clamp(int v, int lo, int hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static int rpm_from_raw(int hi, int lo) {
    if (hi < 0 || lo < 0) return 0;
    uint32_t raw = ((uint32_t)(uint8_t)hi << 8) | (uint32_t)(uint8_t)lo;
    return (raw > 0) ? (int)(2156220 / raw) : 0;
}

static int parse_duty_arg(const char *str) {
    if (!str || !*str) return -1;
    char *endptr = NULL;
    errno = 0;
    long val = strtol(str, &endptr, 10);
    if (errno != 0 || endptr == str || *endptr != '\0') return -1;
    if (val < 0 || val > 100) return -1;
    return (int)val;
}

/* --------------- GPU temp discovery helpers ------------- */

static int gpu_temp_sysfs(void) {
    DIR *d = opendir("/sys/class/hwmon");
    if (!d) return -1;

    int best = -1;
    int rootfd = dirfd(d);
    if (rootfd < 0) { closedir(d); return -1; }

    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (strncmp(de->d_name, "hwmon", 5) != 0) continue;

        int hwfd = openat(rootfd, de->d_name, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (hwfd < 0) continue;

        int namefd = openat(hwfd, "name", O_RDONLY | O_CLOEXEC);
        if (namefd < 0) { close(hwfd); continue; }

        char namebuf[64] = {0};
        ssize_t n = read(namefd, namebuf, sizeof(namebuf) - 1);
        close(namefd);
        if (n <= 0) { close(hwfd); continue; }

        if (!(strstr(namebuf, "nvidia") || strstr(namebuf, "amdgpu") ||
              strstr(namebuf, "i915")   || strstr(namebuf, "xe"))) {
            close(hwfd);
            continue;
        }

        for (int i = 1; i <= 10; i++) {
            char fn[32];
            int m = snprintf(fn, sizeof(fn), "temp%d_input", i);
            if (m < 0 || (size_t)m >= sizeof(fn)) continue;

            int tfd = openat(hwfd, fn, O_RDONLY | O_CLOEXEC);
            if (tfd < 0) continue;

            char buf[32] = {0};
            ssize_t r = read(tfd, buf, sizeof(buf) - 1);
            close(tfd);
            if (r <= 0) continue;

            int milli = atoi(buf);
            if (milli > 0) {
                int c = milli / 1000;
                if (c > best && c < 120) best = c;
            }
        }

        close(hwfd);
    }

    closedir(d);
    return best;
}

/* Safe execution of /usr/bin/nvidia-smi without invoking /bin/sh (avoids popen) */
static int gpu_temp_nvidia_smi(void) {
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
