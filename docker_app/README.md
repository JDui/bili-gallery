# Docker 化 B 站动态相簿 v8.5

## 启动

1. 在仓库根目录执行 `bash docker_app/scripts/bootstrap_macos.sh`
2. 然后执行 `docker compose -f docker_app/docker-compose.example.yml up --build`
3. 打开 `http://localhost:7860`

## NAS 部署

AMD64 NAS 可以直接使用 [docker-compose.nas-amd64.yml](/Users/muxinzheng/Desktop/ZZS/docker_app/docker-compose.nas-amd64.yml)。

建议流程：

1. 先把镜像包导入 NAS：`docker load -i zzs-bili-gallery_v8.5_amd64.tar`
2. 按你的 NAS 实际目录修改 compose 里的两个挂载路径
3. 执行 `docker compose -f docker-compose.nas-amd64.yml up -d`

默认挂载说明：

- `/storage/config` 对应宿主 `config`
- `/storage/data` 对应宿主 `data`

## 审查截图

在本机关闭 Docker 前，可以先生成关键页面截图：

1. 确保已经构建好镜像，例如 `zzs-bili-gallery:amd64`
2. 执行 `bash docker_app/scripts/review_capture.sh zzs-bili-gallery:amd64`
3. 截图会输出到 `docker_app/review/<时间戳>/screens`

## 功能

- 九图动态与 Live Photo 拉取
- 二维码扫码登录与 Cookie 检查
- 推广过滤与待审核列表
- 缩略图 WebP 预生成
- Live Photo 预览、循环、乒乓、单次、不播放
- 原始媒体删除后的缩略图销毁与索引清理

## 数据目录

- `storage/config/app.db`
- `storage/data/images`
- `storage/data/livephoto`
