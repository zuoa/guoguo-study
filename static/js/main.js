// 全局JavaScript功能

// 全局TTS配置缓存（设置为window属性，让所有页面都能访问）
window.globalTTSConfig = null;

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 自动隐藏alert消息
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // 加载TTS配置
    loadTTSConfig();
});

// 加载TTS配置
function loadTTSConfig() {
    fetch('/api/tts-config')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.globalTTSConfig = data.config;
                console.log('TTS配置已加载:', window.globalTTSConfig);
            } else {
                console.warn('加载TTS配置失败，使用默认配置');
                window.globalTTSConfig = {
                    tts_mode: 'auto',
                    server_timeout: 8,
                    browser_rate: 0.8,
                    browser_pitch: 1.0,
                    browser_volume: 1.0,
                    preferred_voice: ''
                };
            }
        })
        .catch(error => {
            console.error('加载TTS配置错误:', error);
            // 使用默认配置
            window.globalTTSConfig = {
                tts_mode: 'auto',
                server_timeout: 8,
                browser_rate: 0.8,
                browser_pitch: 1.0,
                browser_volume: 1.0,
                preferred_voice: ''
            };
        });
}

// 检查浏览器是否支持语音合成
function isBrowserTTSSupported() {
    return 'speechSynthesis' in window;
}

// 浏览器内置语音合成实现（使用配置参数）
function playBrowserTTS(text) {
    if (!isBrowserTTSSupported()) {
        console.warn('Browser speech synthesis not supported');
        return false;
    }
    
    console.log('Using browser speech synthesis for:', text);
    speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    
    // 使用配置中的参数
    if (window.globalTTSConfig) {
        utterance.rate = window.globalTTSConfig.browser_rate;
        utterance.pitch = window.globalTTSConfig.browser_pitch;
        utterance.volume = window.globalTTSConfig.browser_volume;
        
        console.log('Using TTS config:', {
            rate: utterance.rate,
            pitch: utterance.pitch,
            volume: utterance.volume,
            preferred_voice: window.globalTTSConfig.preferred_voice
        });
    } else {
        utterance.rate = 0.8;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;
    }
    
    // 关键修复：等待语音列表加载后再选择语音
    const selectVoiceAndSpeak = () => {
        const voices = speechSynthesis.getVoices();
        let selectedVoice = null;
        
        console.log('Available voices:', voices.map(v => ({name: v.name, lang: v.lang, default: v.default})));
        
        // 首先尝试使用配置中的偏好语音
        if (window.globalTTSConfig && window.globalTTSConfig.preferred_voice) {
            selectedVoice = voices.find(voice => voice.name === window.globalTTSConfig.preferred_voice);
            if (selectedVoice) {
                console.log('Using preferred voice from config:', selectedVoice.name, selectedVoice.lang);
            } else {
                console.warn('Preferred voice not found:', window.globalTTSConfig.preferred_voice);
            }
        }
        
        // 如果没有找到偏好语音，使用默认的英语语音
        if (!selectedVoice) {
            selectedVoice = voices.find(voice => 
                voice.lang.startsWith('en') && voice.default
            ) || voices.find(voice => 
                voice.lang.startsWith('en')
            );
            
            if (selectedVoice) {
                console.log('Using default English voice:', selectedVoice.name, selectedVoice.lang);
            }
        }
        
        if (selectedVoice) {
            utterance.voice = selectedVoice;
        }
        
        utterance.onstart = () => {
            console.log('Browser TTS started for:', text, 'using voice:', selectedVoice ? selectedVoice.name : 'default');
        };
        
        utterance.onend = () => {
            console.log('Browser TTS ended for:', text);
        };
        
        utterance.onerror = (error) => {
            console.error('Browser TTS error:', error);
        };
        
        speechSynthesis.speak(utterance);
    };
    
    // 确保语音列表已加载
    if (speechSynthesis.getVoices().length === 0) {
        console.log('Waiting for voices to load...');
        speechSynthesis.onvoiceschanged = () => {
            console.log('Voices loaded, proceeding with speech');
            selectVoiceAndSpeak();
            speechSynthesis.onvoiceschanged = null; // 避免重复调用
        };
    } else {
        selectVoiceAndSpeak();
    }
    
    return true;
}

// gTTS服务端语音合成实现（使用配置超时）
function playServerTTS(text, onSuccess, onError) {
    console.log('Trying server TTS for:', text);
    
    // 获取配置中的超时时间
    const timeout = window.globalTTSConfig ? window.globalTTSConfig.server_timeout * 1000 : 8000;
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        controller.abort();
        console.log(`Server TTS request timed out after ${timeout/1000}s`);
        onError(new Error('Request timeout'));
    }, timeout);
    
    fetch(`/api/tts/${encodeURIComponent(text)}`, {
        signal: controller.signal
    })
        .then(response => {
            clearTimeout(timeoutId);
            console.log('Server TTS response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Server TTS response:', data);
            if (data.success && data.audio_url) {
                const audio = new Audio();
                
                audio.addEventListener('canplaythrough', () => {
                    console.log('Server TTS audio ready to play');
                    audio.play().then(() => {
                        console.log('Server TTS playing successfully');
                        if (data.cached) {
                            console.log('Using cached audio file');
                        }
                        onSuccess();
                    }).catch(error => {
                        console.error('Audio play error:', error);
                        onError(error);
                    });
                });
                
                audio.addEventListener('error', (e) => {
                    console.error('Audio error:', e);
                    onError(new Error('Audio file load failed'));
                });
                
                audio.src = data.audio_url;
                console.log('Loading audio from:', data.audio_url);
                audio.load();
            } else {
                console.error('Server TTS error:', data.error || 'Audio generation failed');
                onError(new Error(data.error || 'Audio generation failed'));
            }
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.log('Server TTS failed:', error.message);
            onError(error);
        });
}

// 统一的语音播放函数入口（根据配置选择TTS方案）
function playAudio(text, button) {
    if (button && button.disabled) return;
    
    let icon, originalClass;
    if (button) {
        icon = button.querySelector('i');
        originalClass = icon.className;
        icon.className = 'fas fa-spinner fa-spin';
        button.disabled = true;
    }
    
    console.log('Playing audio for:', text);
    console.log('Current globalTTSConfig:', window.globalTTSConfig);
    
    const restoreButton = () => {
        if (button && icon) {
            icon.className = originalClass;
            button.disabled = false;
        }
    };
    
    // 如果配置未加载，使用默认行为
    if (!window.globalTTSConfig) {
        console.warn('TTS配置未加载，使用默认行为');
        if (isBrowserTTSSupported()) {
            setTimeout(() => {
                playBrowserTTS(text);
                restoreButton();
            }, 200);
        } else {
            console.warn('浏览器不支持语音合成');
            restoreButton();
        }
        return;
    }
    
    // 根据配置选择TTS方案
    const mode = window.globalTTSConfig.tts_mode;
    
    if (mode === 'browser') {
        console.log('Using browser TTS (forced by config)');
        if (isBrowserTTSSupported()) {
            setTimeout(() => {
                playBrowserTTS(text);
                restoreButton();
            }, 200);
        } else {
            console.warn('浏览器不支持语音合成');
            restoreButton();
        }
        return;
    }
    
    if (mode === 'server') {
        console.log('Using server TTS (forced by config)');
        playServerTTS(text, 
            () => {
                restoreButton();
            },
            (error) => {
                console.log('Server TTS failed:', error.message);
                restoreButton();
            }
        );
        return;
    }
    
    // auto模式：智能选择
    console.log('Using auto mode for TTS selection');
    
    if (isBrowserTTSSupported()) {
        console.log('Browser TTS supported, using browser TTS');
        setTimeout(() => {
            playBrowserTTS(text);
            restoreButton();
        }, 200);
        return;
    }
    
    console.log('Browser TTS not supported, trying server TTS');
    playServerTTS(text, 
        () => {
            restoreButton();
        },
        (error) => {
            console.log('Server TTS failed, no fallback available:', error.message);
            restoreButton();
        }
    );
}

// 强制使用浏览器TTS的函数（用于用户手动选择浏览器语音的场景）
function playAudioWithBrowserTTS(text, button) {
    if (button && button.disabled) return;
    
    let icon, originalClass;
    if (button) {
        icon = button.querySelector('i');
        originalClass = icon.className;
        
        // 设置加载状态
        icon.className = 'fas fa-volume-up';
        button.disabled = true;
        
        // 1秒后恢复按钮
        setTimeout(() => {
            if (icon) icon.className = originalClass;
            if (button) button.disabled = false;
        }, 1000);
    }
    
    console.log('Force using browser TTS for:', text);
    
    // 直接使用原生浏览器TTS API，但使用全局配置参数
    if ('speechSynthesis' in window) {
        speechSynthesis.cancel();
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-US';
        
        // 使用全局TTS配置中的参数，如果配置未加载则使用默认值
        if (window.globalTTSConfig) {
            utterance.rate = window.globalTTSConfig.browser_rate;
            utterance.pitch = window.globalTTSConfig.browser_pitch;
            utterance.volume = window.globalTTSConfig.browser_volume;
            
            console.log('playAudioWithBrowserTTS using config:', {
                rate: utterance.rate,
                pitch: utterance.pitch,
                volume: utterance.volume,
                preferred_voice: window.globalTTSConfig.preferred_voice
            });
        } else {
            console.log('playAudioWithBrowserTTS config not loaded, using defaults');
            utterance.rate = 0.8;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
        }
        
        const selectVoiceAndSpeak = () => {
            const voices = speechSynthesis.getVoices();
            let selectedVoice = null;
            
            // 首先尝试使用配置中的偏好语音
            if (window.globalTTSConfig && window.globalTTSConfig.preferred_voice) {
                selectedVoice = voices.find(voice => voice.name === window.globalTTSConfig.preferred_voice);
                if (selectedVoice) {
                    console.log('playAudioWithBrowserTTS using preferred voice:', selectedVoice.name, selectedVoice.lang);
                } else {
                    console.warn('playAudioWithBrowserTTS preferred voice not found:', window.globalTTSConfig.preferred_voice);
                }
            }
            
            // 如果没有找到偏好语音，使用默认的英语语音
            if (!selectedVoice) {
                selectedVoice = voices.find(voice => 
                    voice.lang.startsWith('en') && voice.default
                ) || voices.find(voice => 
                    voice.lang.startsWith('en')
                );
                
                if (selectedVoice) {
                    console.log('playAudioWithBrowserTTS using default voice:', selectedVoice.name, selectedVoice.lang);
                }
            }
            
            if (selectedVoice) {
                utterance.voice = selectedVoice;
            }
            
            utterance.onstart = () => console.log('Browser TTS started for:', text);
            utterance.onend = () => console.log('Browser TTS ended for:', text);
            utterance.onerror = (error) => console.error('Browser TTS error:', error);
            
            speechSynthesis.speak(utterance);
        };
        
        if (speechSynthesis.getVoices().length === 0) {
            speechSynthesis.onvoiceschanged = () => {
                selectVoiceAndSpeak();
                speechSynthesis.onvoiceschanged = null; // 避免重复调用
            };
        } else {
            selectVoiceAndSpeak();
        }
        
        console.log('浏览器语音播放');
    } else {
        console.warn('浏览器不支持语音合成');
        // 恢复按钮状态
        if (button && icon) {
            icon.className = originalClass;
            button.disabled = false;
        }
    }
}

// 强制使用服务器TTS的函数（用于用户手动选择服务器语音的场景）
function playAudioWithServerTTS(text, button) {
    if (button && button.disabled) return;
    
    let icon, originalClass;
    if (button) {
        icon = button.querySelector('i');
        originalClass = icon.className;
        
        // 设置加载状态
        icon.className = 'fas fa-spinner fa-spin';
        button.disabled = true;
    }
    
    console.log('Force using server TTS for:', text);
    
    // 恢复按钮状态的函数
    const restoreButton = () => {
        if (button && icon) {
            icon.className = originalClass;
            button.disabled = false;
        }
    };
    
    playServerTTS(text,
        // 成功回调
        () => {
            console.log('服务器语音播放完成');
            restoreButton();
        },
        // 失败回调
        (error) => {
            console.log('Server TTS failed:', error.message);
            restoreButton();
        }
    );
}

// 向后兼容的全局函数（使用全局TTS配置）
window.playBrowserTTS = function(text, button) {
    console.log('Using legacy playBrowserTTS wrapper for:', text);
    
    if (button && button.disabled) return;
    
    let icon, originalClass;
    if (button) {
        icon = button.querySelector('i');
        originalClass = icon.className;
        
        icon.className = 'fas fa-volume-up';
        button.disabled = true;
        
        setTimeout(() => {
            if (icon) icon.className = originalClass;
            if (button) button.disabled = false;
        }, 1000);
    }
    
    // 直接使用原生浏览器TTS API，但使用全局配置参数
    if ('speechSynthesis' in window) {
        speechSynthesis.cancel();
        
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-US';
        
        // 使用全局TTS配置中的参数，如果配置未加载则使用默认值
        if (window.globalTTSConfig) {
            utterance.rate = window.globalTTSConfig.browser_rate;
            utterance.pitch = window.globalTTSConfig.browser_pitch;
            utterance.volume = window.globalTTSConfig.browser_volume;
            
            console.log('legacy playBrowserTTS using config:', {
                rate: utterance.rate,
                pitch: utterance.pitch,
                volume: utterance.volume,
                preferred_voice: window.globalTTSConfig.preferred_voice
            });
        } else {
            console.log('legacy playBrowserTTS config not loaded, using defaults');
            utterance.rate = 0.8;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
        }
        
        const selectVoiceAndSpeak = () => {
            const voices = speechSynthesis.getVoices();
            let selectedVoice = null;
            
            // 首先尝试使用配置中的偏好语音
            if (window.globalTTSConfig && window.globalTTSConfig.preferred_voice) {
                selectedVoice = voices.find(voice => voice.name === window.globalTTSConfig.preferred_voice);
                if (selectedVoice) {
                    console.log('legacy playBrowserTTS using preferred voice:', selectedVoice.name, selectedVoice.lang);
                } else {
                    console.warn('legacy playBrowserTTS preferred voice not found:', window.globalTTSConfig.preferred_voice);
                }
            }
            
            // 如果没有找到偏好语音，使用默认的英语语音
            if (!selectedVoice) {
                selectedVoice = voices.find(voice => 
                    voice.lang.startsWith('en') && voice.default
                ) || voices.find(voice => 
                    voice.lang.startsWith('en')
                );
                
                if (selectedVoice) {
                    console.log('legacy playBrowserTTS using default voice:', selectedVoice.name, selectedVoice.lang);
                }
            }
            
            if (selectedVoice) {
                utterance.voice = selectedVoice;
            }
            
            utterance.onstart = () => console.log('legacy Browser TTS started for:', text);
            utterance.onend = () => console.log('legacy Browser TTS ended for:', text);
            utterance.onerror = (error) => console.error('legacy Browser TTS error:', error);
            
            speechSynthesis.speak(utterance);
        };
        
        if (speechSynthesis.getVoices().length === 0) {
            speechSynthesis.onvoiceschanged = () => {
                selectVoiceAndSpeak();
                speechSynthesis.onvoiceschanged = null; // 避免重复调用
            };
        } else {
            selectVoiceAndSpeak();
        }
        
        console.log('浏览器语音播放');
    } else {
        console.warn('浏览器不支持语音合成');
        if (button && icon) {
            icon.className = originalClass;
            button.disabled = false;
        }
    }
};
window.playAudioDirectly = window.playBrowserTTS;
function confirmDelete(message) {
    return confirm(message || '确定要删除吗？此操作不可恢复。');
}

// 复制到剪贴板
function copyToClipboard(text) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() {
            showToast('已复制到剪贴板');
        });
    } else {
        // 兼容旧浏览器
        const textArea = document.createElement('textarea');
        textArea.value = text;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
        showToast('已复制到剪贴板');
    }
}

// 显示提示消息
function showToast(message, type = 'success') {
    // 创建toast元素
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;
    
    // 添加到页面
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '1055';
        document.body.appendChild(toastContainer);
    }
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    // 显示toast
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    // 自动移除
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// 键盘快捷键支持
document.addEventListener('keydown', function(e) {
    // Escape键返回上级
    if (e.key === 'Escape') {
        const backButton = document.querySelector('a[href*="back"], .btn-secondary[href]');
        if (backButton) {
            backButton.click();
        }
    }
});