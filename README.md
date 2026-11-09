# 全球奇闻

给 Justine 的静态阅读台。每天从公开 RSS 和列表页把奇闻、热帖、部落和各地新奇特捞下来：中文标题和概要、一张主图、原文链接。抓到就放，不按「奇不奇」再筛一遍。

地区标签：非洲、印度、菲律宾、巴基斯坦、部落、其他。美国、巴西、澳大利亚、英国放在「其他」。一条故事可以同时带「部落」和它所在的地区。

打开默认先看猎奇和离谱（适合微信、抖音那种阅读）。暖心动物、节日祝福会标成温情，排到后面，不会删。`python3 scripts/update.py --rescore-only` 只重打分、不重新抓。

## 本地看

```bash
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:43123

页面打开后读取 `/data/stories.json`（开发时来自 `public/data/stories.json`）。第一次如果是空的，先跑更新脚本。

## 更新

只要 Python 3，没有第三方包，也不需要付费 API。中文来自 Google 翻译的公开接口；翻译结果缓存在 `data/translate-cache.json`（不进 git）。同一条原文链接再跑不会重复入库。

```bash
python3 scripts/update.py
```

常用参数：

```bash
python3 scripts/update.py --limit 12          # 每个来源最多几条
python3 scripts/update.py --source bbc-africa # 只跑一个来源，可重复写
python3 scripts/update.py --no-translate      # 跳过翻译，摘要先留原文
```

环境变量：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `ODDNEWS_MAX_PER_SOURCE` | `12` | 每个来源最多收录几条 |
| `ODDNEWS_TRANSLATE` | `1` | 设为 `0` 时不翻译 |
| `ODDNEWS_TIMEOUT` | `18` | 单次请求超时（秒） |

脚本会写三处同一份数据：`data/stories.json`、`public/data/stories.json`，以及已经构建过的 `out/data/stories.json`。页面只请求这份 JSON，所以换一天的内容不用改页面代码，刷新即可。

## 公开地址

目标公开仓库是 `justinethys954-beep/global-qiwen`，页面地址是 https://justinethys954-beep.github.io/global-qiwen/ 。`npm run build` 会带上这个子路径。

Origin 上的 `justine-thys/global-qiwen` 是私有工作副本。GitHub 是公开站点。两边都要更新时，把 `main` 推到两个远程。仓库建好并打开 Pages 之后，每天的 Actions 在 GitHub 上跑：`python3 scripts/update.py` 提交新的 JSON，Pages 工作流再把 `out/` 发布出去。只换数据时不用重新编译页面。

## 静态站点

```bash
npm install
npm run build
```

构建结果在 `out/`。把整个 `out` 目录上传到任意静态托管即可，入口是 `out/index.html`。不要只传 HTML：旁边的 `_next/` 和 `data/stories.json` 必须一起在。

这台环境没有 Cloudflare、Surge 或 Netlify 的登录凭证，也没有接 GitHub，所以没法替你建成一个长期公网地址。你自己上传时用下面任一方式：

1. Cloudflare Pages：新建项目，选 Direct Upload，把 `out` 里的文件拖进去。以后每天只要替换线上的 `data/stories.json`。
2. Surge：`npx surge out 你的名字.surge.sh`，按提示用邮箱注册一次。
3. 任何能放静态文件的地方（对象存储、Nginx）：网站根目录指向 `out/`。

每天更新后，如果站点已经挂着，重新上传 `out/data/stories.json` 就够了。要连页面壳一起换，再跑一次 `npm run build` 然后上传整个 `out/`。

每天跑一次即可，例如：

```cron
0 8 * * * cd /path/to/this/repo && python3 scripts/update.py
```

仓库里也放了 `.github/workflows/daily.yml`，打开 Actions 就能定时跑。

## 加来源

编辑 `sources.json`。`region` 用：

- `africa` 非洲
- `india` 印度
- `philippines` 菲律宾
- `pakistan` 巴基斯坦
- `tribe` 部落 / 原住民 / 偏远族群
- `other` 其他

`kind` 目前有 `rss`、`ndtv-list`、`jsonld-list`、`html-links`。RSS 最省事。标题里如果出现部落、非洲、印度等地名，会额外打上对应标签，所以综合站的部落故事也会进「部落」。

## 图和版权

只存图片 URL，热链到来源站点，不把原图重新上传。页脚写了出处。标题和短导语来自公开 feed，中文是机器翻译，点「阅读原文」看原文。

## 测试

```bash
python3 scripts/test_oddnews.py
```
