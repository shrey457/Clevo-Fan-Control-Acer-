#ifndef EC_LIB_H
#define EC_LIB_H

#ifdef __cplusplus
extern "C" {
#endif

int ec_lib_init(void);
int ec_lib_cpu_temp(void);
int ec_lib_gpu_temp(void);
int ec_lib_fan1_duty_read(void);
int ec_lib_fan2_duty_read(void);
int ec_lib_fan1_rpm_read(void);
int ec_lib_fan2_rpm_read(void);
int ec_lib_fan1_duty_write(int pct);
int ec_lib_fan2_duty_write(int pct);
int ec_lib_fan_set_both(int pct);
int ec_lib_fan_reset(void);

#ifdef __cplusplus
}
#endif

#endif
