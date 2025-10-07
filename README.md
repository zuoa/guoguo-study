# 英语单词学习应用

基于Flask的英语单词学习系统，支持管理端添加章节和学习端听写模式，集成百度翻译API提供准确的中文翻译。

## 功能特点

1. **管理端功能**
   - Auth Code认证登录（从环境变量读取）
   - 添加章节并自动从文本提取单词和短语
   - 章节可自定义名称或使用日期默认命名
   - 管理单词和短语（查看、删除）
   - **百度翻译API测试功能**

2. **学习端功能**
   - 浏览所有章节
   - 学习单词和短语（带发音功能）
   - 听写模式：每次只显示一个单词，支持重复播放
   - **自动中文翻译**（使用百度翻译API）

3. **听写模式特色**
   - 纯听写界面，只显示发音按钮
   - 支持键盘快捷键操作
   - 进度跟踪和完成提示

## 安装说明

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量（参考.env.example文件）：
   - `SECRET_KEY`: Flask密钥
   - `AUTH_CODE`: 管理员认证码
   - `DATABASE_URL`: 数据库路径
   - **`BAIDU_APPID`**: 百度翻译API的APPID
   - **`BAIDU_APPKEY`**: 百度翻译API的密钥

   复制 `.env.example` 为 `.env` 并填入正确的配置值：
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入你的百度翻译API信息
   ```

3. 启动应用：
```bash
python app.py
```

4. 访问地址：
   - 学习端：http://localhost:5000
   - 管理端：http://localhost:5000/admin/login

### 百度翻译API配置
1. 访问 [百度翻译开放平台](https://fanyi-api.baidu.com/)
2. 注册并创建应用，获取APPID和APPKEY
3. 在 `.env` 文件中配置：
   ```
   BAIDU_APPID=你的APPID
   BAIDU_APPKEY=你的APPKEY
   ```
4. 在管理后台点击“测试百度翻译”按钮验证配置

### 使用流程

### 管理端操作
1. 访问 `/admin/login` 使用认证码登录
2. 点击"添加章节"创建新章节
3. 输入章节名称和英文文本内容
4. 系统自动提取单词和短语
5. 在章节管理页面可删除不需要的单词

### 学习端操作
1. 在首页选择要学习的章节
2. 点击"开始学习"查看所有单词和短语
3. 点击发音按钮听取标准读音
4. 点击"听写模式"进入纯听写练习

## 技术栈

- **后端**: Flask, SQLAlchemy, Flask-Login
- **翻译API**: 百度翻译API
- **前端**: Bootstrap 5, Font Awesome
- **数据库**: SQLite
- **语音合成**: Google TTS (gTTS)
- **文本处理**: NLTK

## 目录结构

```
en-study/
├── app.py                 # 主应用文件
├── requirements.txt       # 依赖包列表
├── .env                  # 环境变量配置
├── templates/            # HTML模板
│   ├── base.html
│   ├── index.html        # 学习端首页
│   ├── chapter_detail.html
│   ├── dictation.html    # 听写模式
│   ├── admin_login.html
│   ├── admin_dashboard.html
│   ├── add_chapter.html
│   └── admin_chapter_detail.html
└── static/              # 静态文件
    ├── css/style.css
    ├── js/main.js
    └── audio/           # 生成的音频文件
```

## 特色功能

1. **智能文本解析**: 自动从英文文本中提取单词和常用短语
2. **百度翻译集成**: 使用百度翻译API提供准确的中文翻译
3. **实时语音合成**: 使用Google TTS提供标准英语发音
4. **听写模式**: 专注的听写练习环境，支持键盘快捷键
5. **响应式设计**: 支持桌面和移动设备

## 注意事项

- 首次使用需要联网下载NLTK数据包
- 语音功能需要网络连接（Google TTS）
- 百度翻译API需要网络连接和有效的API凭据
- 生成的音频文件会保存在 `static/audio/` 目录
- 数据库文件 `en_study.db` 会在首次运行时自动创建