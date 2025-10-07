from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from dotenv import load_dotenv
import re
import nltk
from gtts import gTTS
import tempfile
import uuid
import requests
import json
import hashlib
import random
from urllib.parse import quote

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///en_study.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

# 确保下载nltk数据
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')


# 数据库模型
class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, default='admin')


class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    contents = db.relationship('Content', backref='chapter', lazy=True, cascade='all, delete-orphan')
    words = db.relationship('Word', backref='chapter', lazy=True, cascade='all, delete-orphan')
    phrases = db.relationship('Phrase', backref='chapter', lazy=True, cascade='all, delete-orphan')


class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(300), nullable=False)  # 统一存储单词或短语
    translation = db.Column(db.String(400))
    phonetic = db.Column(db.String(200))
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=False)
    created_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# 保留原有模型以兼容现有数据
class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), nullable=False)
    translation = db.Column(db.String(200))
    phonetic = db.Column(db.String(100))
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=False)


class Phrase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phrase = db.Column(db.String(300), nullable=False)
    translation = db.Column(db.String(400))
    phonetic = db.Column(db.String(200))
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=False)


class TTSConfig(db.Model):
    """TTS配置模型"""
    id = db.Column(db.Integer, primary_key=True)
    # TTS模式：'server' 服务器TTS，'browser' 浏览器TTS，'auto' 自动选择
    tts_mode = db.Column(db.String(20), nullable=False, default='auto')
    # 服务器TTS超时时间（秒）
    server_timeout = db.Column(db.Integer, default=8)
    # 浏览器TTS语速（0.1-10，默认0.8）
    browser_rate = db.Column(db.Float, default=0.8)
    # 浏览器TTS音调（0-2，默认1）
    browser_pitch = db.Column(db.Float, default=1.0)
    # 浏览器TTS音量（0-1，默认1）
    browser_volume = db.Column(db.Float, default=1.0)
    # 偏好的语音名称
    preferred_voice = db.Column(db.String(100), default='')
    # 创建时间
    created_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # 更新时间
    updated_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


def get_tts_config():
    """获取TTS配置，如果不存在则创建默认配置"""
    config = TTSConfig.query.first()
    if not config:
        config = TTSConfig(
            tts_mode='auto',
            server_timeout=8,
            browser_rate=0.8,
            browser_pitch=1.0,
            browser_volume=1.0,
            preferred_voice=''
        )
        db.session.add(config)
        db.session.commit()
    return config


def update_tts_config(data):
    """更新TTS配置"""
    config = get_tts_config()
    
    if 'tts_mode' in data:
        mode = data['tts_mode']
        if mode in ['server', 'browser', 'auto']:
            config.tts_mode = mode
    
    if 'server_timeout' in data:
        timeout = int(data['server_timeout'])
        if 3 <= timeout <= 30:  # 限制在3-30秒之间
            config.server_timeout = timeout
    
    if 'browser_rate' in data:
        rate = float(data['browser_rate'])
        if 0.1 <= rate <= 10.0:  # 语速范围限制
            config.browser_rate = rate
    
    if 'browser_pitch' in data:
        pitch = float(data['browser_pitch'])
        if 0.0 <= pitch <= 2.0:  # 音调范围限制
            config.browser_pitch = pitch
    
    if 'browser_volume' in data:
        volume = float(data['browser_volume'])
        if 0.0 <= volume <= 1.0:  # 音量范围限制
            config.browser_volume = volume
    
    if 'preferred_voice' in data:
        config.preferred_voice = data['preferred_voice']
    
    config.updated_date = datetime.utcnow()
    db.session.commit()
    return config


def get_baidu_translation(text, from_lang='en', to_lang='zh'):
    """使用百度翻译API获取翻译"""
    try:
        # 从环境变量获取appid和appkey
        appid = os.getenv('BAIDU_APPID')
        appkey = os.getenv('BAIDU_APPKEY')
        
        if not appid or not appkey:
            print('百度翻译API配置缺失，请设置BAIDU_APPID和BAIDU_APPKEY环境变量')
            return get_chinese_translation_fallback(text)  # 使用备用方法
        
        # 构建请求参数
        salt = str(random.randint(32768, 65536))
        
        # 构建签名字符串
        sign_str = appid + text + salt + appkey
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
        
        # 请求参数
        params = {
            'q': text,
            'from': from_lang,
            'to': to_lang,
            'appid': appid,
            'salt': salt,
            'sign': sign
        }
        
        # 发送请求
        url = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            
            # 检查是否有错误
            if 'error_code' in result:
                print(f"百度翻译API错误: {result.get('error_msg', '未知错误')}")
                return get_chinese_translation_fallback(text)
            
            # 提取翻译结果
            if 'trans_result' in result and result['trans_result']:
                translation = result['trans_result'][0]['dst']
                return translation
        
        print(f"百度翻译API请求失败，状态码: {response.status_code}")
        return get_chinese_translation_fallback(text)
        
    except Exception as e:
        print(f"百度翻译API异常: {str(e)}")
        return get_chinese_translation_fallback(text)


def get_chinese_translation_fallback(text):
    """获取中文翻译"""
    try:
        # 使用百度翻译API或其他中文翻译服务
        # 这里先使用一个简单的获取方式
        # TODO: 集成真正的中文翻译API
        
        # 先尝试使用Dictionary API获取英文释义
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{text.lower().replace(' ', '%20')}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                meanings = data[0].get('meanings', [])
                if meanings:
                    definitions = meanings[0].get('definitions', [])
                    if definitions:
                        definition = definitions[0].get('definition', '')
                        # 返回英文释义（作为中文翻译的替代）
                        return definition[:150] if definition else ""
        
        return ""
    except Exception as e:
        print(f"Translation API Error for '{text}': {str(e)}")
        return ""


def get_chinese_translation(text):
    """获取中文翻译，优先使用百度翻译API"""
    # 优先使用百度翻译API
    return get_baidu_translation(text)


def get_phonetic(word):
    """获取单词音标"""
    try:
        # 使用免费的音标API
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.lower()}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                # 获取第一个结果的音标
                phonetics = data[0].get('phonetics', [])
                for phonetic in phonetics:
                    if phonetic.get('text'):
                        return phonetic['text']
        
        # 如果 API 失败，返回空字符串
        return ""
    except Exception as e:
        print(f"Phonetic API Error for '{word}': {str(e)}")
        return ""


def extract_content_items(text):
    """按空格数量分割文本内容：2个或更多空格分为一组"""
    if not text or not text.strip():
        return []
    
    # 清理文本，保留字母、数字、空格、连字符、撇号和基本标点
    text = re.sub(r'[^\w\s\-\'\.,;:!?()]', ' ', text)
    
    # 先处理换行符，然后处理每一行
    lines = text.split('\n')
    all_items = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 按2个或更多空格分割（包括制表符）
        line_items = re.split(r'[ \t]{2,}', line)
        
        for item in line_items:
            # 清理首尾的标点符号和空格
            item = item.strip(' .,;:!?()')
            
            # 过滤条件：长度至少2个字符，且包含至少一个字母
            if item and len(item) >= 2 and re.search(r'[a-zA-Z]', item):
                # 标准化内部空格（只处理多个连续空格）
                item = re.sub(r'[ \t]+', ' ', item)
                all_items.append(item)
    
    # 去除重复项目，保持顺序
    seen = set()
    unique_items = []
    for item in all_items:
        item_lower = item.lower().strip()
        if item_lower and item_lower not in seen:
            seen.add(item_lower)
            unique_items.append(item)
    
    return unique_items


# 路由
@app.route('/')
def index():
    """学习端首页"""
    chapters = Chapter.query.order_by(Chapter.created_date.desc()).all()
    return render_template('index.html', chapters=chapters)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """管理端登录"""
    if request.method == 'POST':
        auth_code = request.form.get('auth_code')
        if auth_code == os.getenv('AUTH_CODE'):
            # 获取或创建admin用户
            admin = Admin.query.first()
            if not admin:
                admin = Admin(username='admin')
                db.session.add(admin)
                db.session.commit()

            login_user(admin)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('认证码错误', 'error')

    return render_template('admin_login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin_dashboard():
    """管理端仪表板"""
    chapters = Chapter.query.order_by(Chapter.created_date.desc()).all()
    return render_template('admin_dashboard.html', chapters=chapters)


@app.route('/admin/chapter/add', methods=['GET', 'POST'])
@login_required
def add_chapter():
    """添加章节 - 第一步：预览分割"""
    if request.method == 'POST':
        name = request.form.get('name')
        text_content = request.form.get('text_content')

        if not name:
            name = datetime.now().strftime('%Y-%m-%d')

        # 如果有文本内容，先预览分割结果
        if text_content:
            items = extract_content_items(text_content)
            if items:
                # 存储在session中用于下一步确认
                session['chapter_name'] = name
                session['content_items'] = items
                return redirect(url_for('preview_content_split'))
            else:
                flash('未能从文本中提取有效内容，请检查文本格式', 'warning')
        else:
            # 如果没有文本内容，直接创建空章节
            chapter = Chapter(name=name)
            db.session.add(chapter)
            db.session.commit()
            flash(f'空章节 "{name}" 创建成功！', 'success')
            return redirect(url_for('admin_dashboard'))

    return render_template('add_chapter.html')


@app.route('/admin/chapter/preview-split')
@login_required
def preview_content_split():
    """预览内容分割结果"""
    chapter_name = session.get('chapter_name')
    content_items = session.get('content_items')
    
    if not chapter_name or not content_items:
        flash('会话已过期，请重新提交', 'error')
        return redirect(url_for('add_chapter'))
    
    return render_template('preview_split.html', 
                         chapter_name=chapter_name, 
                         content_items=content_items)


@app.route('/admin/chapter/confirm-split', methods=['POST'])
@login_required
def confirm_content_split():
    """确认分割并创建章节"""
    chapter_name = session.get('chapter_name')
    content_items = session.get('content_items')
    
    if not chapter_name or not content_items:
        flash('会话已过期，请重新提交', 'error')
        return redirect(url_for('add_chapter'))
    
    # 获取用户修改后的内容
    confirmed_items = request.form.getlist('content_items')
    confirmed_items = [item.strip() for item in confirmed_items if item.strip()]
    
    if not confirmed_items:
        flash('没有有效的内容项目', 'warning')
        return redirect(url_for('preview_content_split'))
    
    try:
        # 创建章节
        chapter = Chapter(name=chapter_name)
        db.session.add(chapter)
        db.session.commit()
        
        # 清除session
        session.pop('chapter_name', None)
        session.pop('content_items', None)
        
        flash(f'章节 "{chapter_name}" 创建成功！正在后台获取音标和翻译...', 'success')
        
        # 异步处理音标和翻译
        return redirect(url_for('process_content_async', chapter_id=chapter.id, items=','.join(confirmed_items)))
        
    except Exception as e:
        db.session.rollback()
        flash(f'创建章节失败: {str(e)}', 'error')
        return redirect(url_for('preview_content_split'))


@app.route('/admin/chapter/<int:chapter_id>/process-content')
@login_required
def process_content_async(chapter_id):
    """异步处理内容，获取音标和翻译"""
    chapter = Chapter.query.get_or_404(chapter_id)
    items_str = request.args.get('items', '')
    items = [item.strip() for item in items_str.split(',') if item.strip()]
    
    if not items:
        flash('没有内容需要处理', 'warning')
        return redirect(url_for('admin_chapter_detail', chapter_id=chapter_id))
    
    return render_template('process_loading.html', 
                         chapter=chapter, 
                         items=items)


@app.route('/api/process-content-item', methods=['POST'])
@login_required
def process_content_item():
    """处理单个内容项，获取音标和翻译"""
    data = request.get_json()
    chapter_id = data.get('chapter_id')
    text = data.get('text')
    
    if not chapter_id or not text:
        return jsonify({'success': False, 'error': '参数缺失'})
    
    try:
        chapter = Chapter.query.get_or_404(chapter_id)
        
        # 获取音标和翻译
        phonetic = get_phonetic(text)
        translation = get_chinese_translation(text)
        
        # 创建内容项
        content = Content(
            text=text,
            phonetic=phonetic,
            translation=translation,
            chapter_id=chapter_id
        )
        db.session.add(content)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'phonetic': phonetic,
            'translation': translation
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/chapter/<int:chapter_id>')
@login_required
def admin_chapter_detail(chapter_id):
    """管理端章节详情"""
    chapter = Chapter.query.get_or_404(chapter_id)
    return render_template('admin_chapter_detail.html', chapter=chapter)


@app.route('/chapter/<int:chapter_id>')
def chapter_detail(chapter_id):
    """学习端章节详情"""
    chapter = Chapter.query.get_or_404(chapter_id)
    return render_template('chapter_detail.html', chapter=chapter)


@app.route('/chapter/<int:chapter_id>/dictation')
def dictation_mode(chapter_id):
    """听写模式"""
    chapter = Chapter.query.get_or_404(chapter_id)
    return render_template('dictation.html', chapter=chapter)


@app.route('/admin/content/<int:content_id>/delete', methods=['POST'])
@login_required
def delete_content(content_id):
    """删除内容项"""
    content = Content.query.get_or_404(content_id)
    chapter_id = content.chapter_id
    db.session.delete(content)
    db.session.commit()
    flash('内容删除成功', 'success')
    return redirect(url_for('admin_chapter_detail', chapter_id=chapter_id))


@app.route('/api/test-translation', methods=['POST'])
@login_required
def test_translation():
    """测试百度翻译API"""
    data = request.get_json()
    text = data.get('text', 'hello')
    
    try:
        # 测试百度翻译
        translation = get_baidu_translation(text)
        
        return jsonify({
            'success': True,
            'original': text,
            'translation': translation,
            'method': 'baidu_api'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@app.route('/api/test-tts')
def test_tts():
    """测试TTS功能"""
    try:
        # 测试一个简单的单词
        word = "hello"
        print(f"Testing TTS for: {word}")
        
        # 确保音频目录存在
        audio_dir = os.path.join('static', 'audio')
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir)
            print(f"Created audio directory: {audio_dir}")
        
        # 设置超时时间
        import socket
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(3)  # 测试时设置更短的超时
        
        try:
            tts = gTTS(text=word, lang='en')
            filename = f"test_{uuid.uuid4()}.mp3"
            filepath = os.path.join(audio_dir, filename)
            
            print(f"Saving test audio to: {filepath}")
            
            # 获取TTS配置中的超时设置
            config = get_tts_config()
            timeout = config.server_timeout
            
            # 设置超时时间
            socket.setdefaulttimeout(timeout)
            tts.save(filepath)
            
            if os.path.exists(filepath):
                audio_url = f'/static/audio/{filename}'
                print(f"Test audio generated successfully: {audio_url}")
                return jsonify({
                    'success': True, 
                    'message': 'TTS功能正常',
                    'audio_url': audio_url,
                    'test_word': word
                })
            else:
                return jsonify({
                    'success': False, 
                    'error': '测试音频文件未生成'
                })
                
        except Exception as gtts_error:
            print(f"gTTS test error: {str(gtts_error)}")
            return jsonify({
                'success': False, 
                'error': f'gTTS错误: {str(gtts_error)}'
            })
        finally:
            socket.setdefaulttimeout(original_timeout)
            
    except Exception as e:
        print(f"Test TTS Error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/tts/<word>')
def text_to_speech(word):
    """文本转语音API - 带备用方案"""
    try:
        print(f"TTS request for: {word}")  # 添加调试日志
        
        # 获取TTS配置
        config = get_tts_config()
        
        # 确保音频目录存在
        audio_dir = os.path.join('static', 'audio')
        if not os.path.exists(audio_dir):
            os.makedirs(audio_dir)
            print(f"Created audio directory: {audio_dir}")
        
        # 检查目录权限
        if not os.access(audio_dir, os.W_OK):
            print(f"No write permission for: {audio_dir}")
            return jsonify({'error': '音频目录没有写入权限', 'success': False}), 500
        
        # 先尝试使用缓存的音频文件
        word_hash = hashlib.md5(word.encode('utf-8')).hexdigest()[:8]
        cached_filename = f"cached_{word_hash}.mp3"
        cached_filepath = os.path.join(audio_dir, cached_filename)
        
        if os.path.exists(cached_filepath):
            print(f"Using cached audio: {cached_filepath}")
            audio_url = f'/static/audio/{cached_filename}'
            return jsonify({'audio_url': audio_url, 'success': True, 'cached': True})
        
        # 尝试生成新的音频文件
        import socket
        import signal
        import threading
        original_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(config.server_timeout)  # 使用配置中的超时时间
        
        def timeout_handler():
            """超时后强制返回备用方案"""
            import time
            time.sleep(config.server_timeout)
            raise Exception('请求超时')
        
        try:
            print(f"Generating new audio for: {word}")
            
            # 使用线程控制超时
            tts_success = False
            tts_error = None
            
            def generate_tts():
                nonlocal tts_success, tts_error
                try:
                    tts = gTTS(text=word, lang='en')
                    tts.save(cached_filepath)
                    # 检查文件是否成功生成且非空
                    if os.path.exists(cached_filepath) and os.path.getsize(cached_filepath) > 0:
                        tts_success = True
                    else:
                        tts_error = Exception('生成的音频文件为空')
                except Exception as e:
                    tts_error = e
            
            # 启动TTS生成线程
            tts_thread = threading.Thread(target=generate_tts)
            tts_thread.daemon = True
            tts_thread.start()
            
            # 等待指定的超时时间
            tts_thread.join(timeout=config.server_timeout)
            
            if tts_thread.is_alive():
                # 超时了，直接返回备用方案
                print(f"TTS generation timed out for: {word} after {config.server_timeout}s")
                return jsonify({
                    'success': False,
                    'error': 'TTS服务超时，建议使用浏览器语音',
                    'fallback': True,
                    'message': '请使用浏览器内置语音功能'
                }), 503
            
            if not tts_success:
                # 生成失败
                error_msg = str(tts_error) if tts_error else 'TTS生成失败'
                print(f"TTS generation failed: {error_msg}")
                return jsonify({
                    'success': False,
                    'error': f'语音服务不可用：{error_msg}',
                    'fallback': True,
                    'message': '请使用浏览器内置语音功能'
                }), 503
            
            # 返回成功结果
            audio_url = f'/static/audio/{cached_filename}'
            print(f"Audio generated successfully: {audio_url}")
            return jsonify({'audio_url': audio_url, 'success': True, 'cached': False})
            
        except Exception as gtts_error:
            print(f"gTTS Error: {str(gtts_error)}")
            
            # 如果gTTS失败，返回备用方案响应
            print(f"TTS service unavailable, returning fallback response")
            return jsonify({
                'success': False,
                'error': f'语音服务不可用：{str(gtts_error)}',
                'fallback': True,
                'message': '请使用浏览器内置语音功能'
            }), 503
            
        finally:
            # 恢复原始超时设置
            socket.setdefaulttimeout(original_timeout)
        
    except Exception as e:
        print(f"TTS Error: {str(e)}")  # 添加调试日志
        import traceback
        print(f"TTS Error traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e), 'success': False}), 500


@app.route('/admin/word/<int:word_id>/delete', methods=['POST'])
@login_required
def delete_word(word_id):
    """删除单词"""
    word = Word.query.get_or_404(word_id)
    chapter_id = word.chapter_id
    db.session.delete(word)
    db.session.commit()
    flash('单词删除成功', 'success')
    return redirect(url_for('admin_chapter_detail', chapter_id=chapter_id))


@app.route('/admin/phrase/<int:phrase_id>/delete', methods=['POST'])
@login_required
def delete_phrase(phrase_id):
    """删除短语"""
    phrase = Phrase.query.get_or_404(phrase_id)
    chapter_id = phrase.chapter_id
    db.session.delete(phrase)
    db.session.commit()
    flash('短语删除成功', 'success')
    return redirect(url_for('admin_chapter_detail', chapter_id=chapter_id))


@app.route('/api/tts-config', methods=['GET', 'POST'])
def tts_config_api():
    """TTS配置API"""
    if request.method == 'GET':
        # 获取当前配置
        config = get_tts_config()
        return jsonify({
            'success': True,
            'config': {
                'tts_mode': config.tts_mode,
                'server_timeout': config.server_timeout,
                'browser_rate': config.browser_rate,
                'browser_pitch': config.browser_pitch,
                'browser_volume': config.browser_volume,
                'preferred_voice': config.preferred_voice
            }
        })
    
    elif request.method == 'POST':
        # 更新配置
        try:
            data = request.get_json()
            config = update_tts_config(data)
            return jsonify({
                'success': True,
                'message': '配置更新成功',
                'config': {
                    'tts_mode': config.tts_mode,
                    'server_timeout': config.server_timeout,
                    'browser_rate': config.browser_rate,
                    'browser_pitch': config.browser_pitch,
                    'browser_volume': config.browser_volume,
                    'preferred_voice': config.preferred_voice
                }
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'配置更新失败: {str(e)}'
            }), 400


@app.route('/api/browser-voices')
def get_browser_voices():
    """获取可用的浏览器语音列表（前端调用后返回）"""
    return jsonify({
        'success': True,
        'message': '请在前端调用speechSynthesis.getVoices()获取语音列表'
    })


if __name__ == '__main__':
    with app.app_context():
        # 创建表，如果表已存在则添加新列
        db.create_all()
        
        # 检查并添加内容表
        try:
            db.session.execute(db.text("SELECT id FROM content LIMIT 1"))
        except Exception:
            try:
                db.session.execute(db.text("""CREATE TABLE content (
                    id INTEGER PRIMARY KEY,
                    text VARCHAR(300) NOT NULL,
                    translation VARCHAR(400),
                    phonetic VARCHAR(200),
                    chapter_id INTEGER NOT NULL,
                    created_date DATETIME NOT NULL,
                    FOREIGN KEY(chapter_id) REFERENCES chapter(id)
                )"""))
                db.session.commit()
                print("内容表创建成功")
            except Exception as e:
                print(f"创建内容表失败: {e}")
        
        # 检查并添加TTS配置表
        try:
            db.session.execute(db.text("SELECT id FROM tts_config LIMIT 1"))
        except Exception:
            try:
                db.session.execute(db.text("""CREATE TABLE tts_config (
                    id INTEGER PRIMARY KEY,
                    tts_mode VARCHAR(20) NOT NULL DEFAULT 'auto',
                    server_timeout INTEGER DEFAULT 8,
                    browser_rate FLOAT DEFAULT 0.8,
                    browser_pitch FLOAT DEFAULT 1.0,
                    browser_volume FLOAT DEFAULT 1.0,
                    preferred_voice VARCHAR(100) DEFAULT '',
                    created_date DATETIME NOT NULL,
                    updated_date DATETIME NOT NULL
                )"""))
                db.session.commit()
                print("TTS配置表创建成功")
            except Exception as e:
                print(f"创建TTS配置表失败: {e}")
                
    app.run(debug=True)
