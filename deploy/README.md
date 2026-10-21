# 自有服务器部署（Docker Compose）

目标：在自有服务器上运行后端容器，复用现有 MySQL，先用
`http://服务器IP:8000` 联调，后续再上 HTTPS 域名。

## 前置条件

- 服务器已安装 Docker 和 Docker Compose v2（Portainer 已在运行）。
- 服务器已放行 TCP 8000：阿里云安全组和系统防火墙都要检查。
- 仓库已放到服务器，例如 `/opt/ai-learn`。
- 现有 MySQL 容器：`mysql`，宿主机端口 `3306`，库名 `ai_learn`。

## 1. 准备环境变量

```bash
cd /opt/ai-learn
cp backend/.env.example backend/.env
vim backend/.env
```

至少填写：

- `DEEPSEEK_API_KEY`
- `WECHAT_APPID`、`WECHAT_APPSECRET`
- `MYSQL_USER`、`MYSQL_PASSWORD`
- `JWT_SECRET`

知识库和题目配图再填写 `DASHSCOPE_API_KEY`、`COS_*`。

本机开发用的 `backend/.env` 可能填写外网 MySQL 地址，该文件已被 Git 忽略，
不会提交到仓库。容器内由 `docker-compose.yml` 覆盖为 MySQL 容器名：

```yaml
MYSQL_HOST: mysql
MYSQL_PORT: "3306"
```

需要先把 MySQL 容器接入 Compose 网络，见第 5 节。

## 2. 构建并启动

```bash
cd /opt/ai-learn
docker compose up -d --build
docker compose logs -f backend
```

首次构建需要下载 Python 依赖，耗时较长。看到 `app_startup_complete`
后另开终端验证：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## 3. 用 Portainer 管理

部署成功后，Portainer 的 **Containers** 会出现 `ai-learn-backend`，
可以在网页里看日志、重启、进入 Console。

注意：

- Portainer 的 **Stacks** 页面只列出通过 Portainer 自己创建的栈；
  用 SSH 执行 `docker compose` 部署的项目不一定出现在 Stacks 里，但不影响在
  Containers 中管理。
- Portainer 的 **Web editor** 只保存 YAML，不会上传源码，`build: .` 会找不到代码。
- **Repository** 模式会拉取 Git 仓库，但 `backend/.env` 被 git 忽略，不会进仓库。
- 因此首次部署建议用 SSH 执行 `docker compose up -d --build`，
  Portainer 负责日常查看和重启。

## 4. 放行端口

当前只映射宿主机 8000：

1. 阿里云安全组入方向放行 TCP 8000。
2. 如果系统启用了 firewalld/ufw，也要放行 8000。
3. 浏览器访问 `http://服务器IP:8000/api/v1/health`。

8000 只是联调端口。微信小程序正式环境必须使用 HTTPS 域名，
不能直接填 IP + HTTP。

## 5. MySQL 连接

Compose 通过容器名 `mysql` 访问现有 MySQL，因此需要先把 MySQL 容器接入
Compose 网络（只需执行一次）：

```bash
docker network ls | grep ai-learn
docker network connect ai-learn_default mysql
```

如果网络名不是 `ai-learn_default`，使用上一条命令输出里的实际名称。
MySQL 容器重建后，需要重新执行 `docker network connect`。

然后重启后端：

```bash
docker compose up -d --force-recreate
docker compose logs --tail=100 backend | grep -E "mysql_pool_ready|mysql_init_failed"
```

如果不想接入 Compose 网络，也可以把 `docker-compose.yml` 里的
`MYSQL_HOST` 改成 `host.docker.internal`，并恢复 `extra_hosts`；
具体地址只写在 `backend/.env`，不要提交到仓库。

`MYSQL_AUTO_INIT=true` 会在启动时执行 `sql/init_mysql.sql`。建表语句都是
`IF NOT EXISTS`，不会删除现有数据。如果数据库账号没有建库权限，改成 `false`，
先手动导入 SQL。

## 6. 数据持久化

Compose 使用两个命名卷：

- `ai_learn_data` → `/app/backend/data`：Chroma 向量库、知识库上传文件。
- `ai_learn_logs` → `/app/backend/logs`：滚动日志。

重建容器不会丢数据，删除卷才会。备份示例：

```bash
docker run --rm -v ai_learn_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/ai_learn_data.tgz -C /data .
```

如果本机已经上传过知识库文档，本机的 `backend/data/knowledge_base` 和
`backend/data/chroma` 不会自动进入命名卷。需要把这两个目录迁移到
`ai_learn_data` 卷，或者部署后在页面上重新上传文档重建索引；否则数据库里
已有文档记录会找不到原文件和向量。

## 7. 前端联调地址

前端 API 地址由 Taro 环境文件控制：

- `.env.development`：开发/联调地址，默认 `http://127.0.0.1:8000`
- `.env.production`：生产地址，上线前替换成真实 HTTPS 域名

`npm run dev:weapp` 读取 development，`npm run build:weapp` 读取 production。

## 8. 后续上 HTTPS

有域名和证书后，参考 `deploy/nginx.conf.example` 配置宿主机 Nginx，
把 443 反向代理到 `127.0.0.1:8000`，并在微信公众平台配置
request/uploadFile/downloadFile 合法域名。中国大陆服务器还需要域名备案。

## 9. 更新版本

```bash
cd /opt/ai-learn
git pull
docker compose up -d --build
```
