# B 站动态相簿

这是一个面向个人收藏场景的 B 站动态相簿项目，包含两部分能力：

- 根目录脚本：用于拉取九图动态与 Live Photo 数据
- `docker_app/`：用于浏览、筛选和管理媒体资源的 Web 应用

项目当前内置版本为 `v6.2`，适合在 macOS 本地运行，也支持 AMD64 NAS 通过 Docker 部署。

## 功能概览

- 拉取 B 站九图动态图片
- 拉取 Live Photo 动图资源
- 扫码登录与 Cookie 状态检查
- 推广内容过滤与待审核列表
- 图片缩略图预生成
- Live Photo 多种播放模式
- 原始媒体删除后的索引与缩略图清理

## 目录说明

```text
.
├── bili_9pics_downloader.py        # 九图动态拉取脚本
├── LivePhoto/                      # Live Photo 拉取相关脚本与输入文件
├── docker_app/                     # Web 应用、Docker 配置、测试与脚本
├── urls_9pics.txt                  # 九图动态链接输入
├── downloads.md                    # 九图动态下载记录
└── storage/                        # 运行时数据目录，不纳入版本控制
```

运行时数据默认写入：

- `storage/config/app.db`
- `storage/data/images`
- `storage/data/livephoto`

## 本地启动 Web 应用

适合在 macOS 上直接预览和开发。

1. 在仓库根目录执行：

```bash
bash docker_app/scripts/bootstrap_macos.sh
```

2. 启动容器：

```bash
docker compose -f docker_app/docker-compose.example.yml up --build
```

3. 打开浏览器访问：

```text
http://localhost:7860
```

默认挂载当前仓库目录，并将 `storage/` 作为应用数据目录。

## NAS 部署

仓库提供了 AMD64 NAS 的 Compose 示例文件：

- [`docker_app/docker-compose.nas-amd64.yml`](/Users/muxinzheng/Desktop/ZZS/docker_app/docker-compose.nas-amd64.yml)

推荐部署流程：

1. 从 Release 下载最新镜像包
2. 导入镜像：

```bash
docker load -i zzs-bili-gallery_v6.2_amd64.tar
```

3. 按实际环境修改 `docker_app/docker-compose.nas-amd64.yml` 中的挂载路径
4. 启动服务：

```bash
docker compose -f docker_app/docker-compose.nas-amd64.yml up -d
```

默认端口：

- `7860`

关键环境变量：

- `APP_REPO_ROOT=/workspace`
- `APP_STORAGE_ROOT=/storage`
- `TZ=Asia/Shanghai`

## 已编译版本

当前仓库内最新已编译镜像包为：

- `docker_app/dist/zzs-bili-gallery_v6.2_amd64.tar`

该文件适合上传到 GitHub Releases，供 NAS 或其他 Docker 环境直接导入使用。

## 数据抓取脚本

根目录和 `LivePhoto/` 目录中保留了原始抓取脚本，可用于补充或刷新素材数据：

- `bili_9pics_downloader.py`
- `LivePhoto/bili_livephoto_downloader.py`

输入与记录文件：

- `urls_9pics.txt`
- `downloads.md`
- `LivePhoto/urls_livephoto.txt`
- `LivePhoto/downloads_livephoto.md`

## 开发与测试

测试文件位于：

- `docker_app/tests/test_rules.py`

如果需要生成页面审查截图，可执行：

```bash
bash docker_app/scripts/review_capture.sh zzs-bili-gallery:amd64
```

输出目录：

- `docker_app/review/<时间戳>/screens`

## 注意事项

- `storage/`、日志文件、构建产物和本地缓存不应提交到 Git
- Release 包体积较大，上传前建议保留 `.sha256` 校验文件
- 若当前终端未继承系统代理，访问 GitHub 时需要显式设置 `HTTP_PROXY` 与 `HTTPS_PROXY`
