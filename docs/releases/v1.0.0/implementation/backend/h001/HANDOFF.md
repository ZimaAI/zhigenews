# 后端交接 v1.0.0/h001

规范：v1.0.0/b003；代码：994e069c0cb3b688248efd3deb7ec0bc1fd522b0 + uncommitted backend snapshot 64fd2c11f1b643bc0a53615de685626d303f55c735d7254d7f8e20548b9e42f0。

先读 handoff.json 指向的运行、接口、环境与冒烟说明；契约在 contracts/。
本包不包含生产密钥，不替代批准规范和原型，不证明远程服务当前在线。
新会话应重新启动/探测服务并取得 frontend 阶段授权，不能沿用旧进程句柄。
