# Docker 化 B 站动态相簿 v9.9

## 启动

1. 在仓库根目录执行 `bash docker_app/scripts/bootstrap_macos.sh`
2. 然后执行 `docker compose -f docker_app/docker-compose.example.yml up --build`
3. 打开 `http://localhost:7860`

## NAS 部署

AMD64 NAS 可以直接使用 [docker-compose.nas-amd64.yml](/Users/muxinzheng/Desktop/ZZS/docker_app/docker-compose.nas-amd64.yml)。

建议流程：

1. 先把镜像包导入 NAS：`docker load -i zzs-bili-gallery_v9.9_amd64.tar`
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
- 相似图片重复内容检测与贴文集中处理
- 缩略图 WebP 预生成
- Live Photo 预览、循环、乒乓、单次、不播放
- 原始媒体删除后的缩略图销毁与索引清理
- 前台加载优先调度，后台拉取、删除、图标刷新和重复检测会主动让行

## 任务优先级

- 前台任务：页面、瀑布流、详情、缩略图及媒体内容加载
- 后台任务：拉取、删除与文件清理、图标获取、重复检测、索引和缩略图重建
- 前后台同时发生时，后台任务会在处理步骤之间等待前台请求完成；缩略图后台并发默认限制为 1

## 数据目录

- `storage/config/app.db`
- `storage/data/images`
- `storage/data/livephoto`
