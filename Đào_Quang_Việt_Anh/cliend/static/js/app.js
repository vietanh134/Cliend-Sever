/**
 * TCP Socket Pro Terminal - Web Frontend Logic & Rich Media File Support
 */

document.addEventListener('DOMContentLoaded', () => {
    // State variables
    let currentState = {
        connected: false,
        connecting: false,
        host: "172.20.10.4",
        port: 9000,
        local_server_active: false,
        stats: { sent_count: 0, recv_count: 0, files_sent: 0, files_recv: 0, bytes_sent: 0, bytes_recv: 0 }
    };

    let messagesList = [];
    let activeFilter = 'all';
    let soundEnabled = true;
    let selectedFile = null; // Currently attached pending file
    let eventSource = null;

    // DOM Element Selectors
    const targetIpInput = document.getElementById('targetIp');
    const targetPortInput = document.getElementById('targetPort');
    const btnConnect = document.getElementById('btnConnect');
    const connectBtnText = document.getElementById('connectBtnText');
    const btnLocalServer = document.getElementById('btnLocalServer');
    const localServerText = document.getElementById('localServerText');

    const statusBadge = document.getElementById('statusBadge');
    const statusText = document.getElementById('statusText');
    const displayIp = document.getElementById('displayIp');
    const displayPort = document.getElementById('displayPort');
    const displayConnectedAt = document.getElementById('displayConnectedAt');

    const statSent = document.getElementById('statSent');
    const statRecv = document.getElementById('statRecv');
    const statFilesSent = document.getElementById('statFilesSent');
    const statFilesRecv = document.getElementById('statFilesRecv');
    const statBytesSent = document.getElementById('statBytesSent');
    const statBytesRecv = document.getElementById('statBytesRecv');

    const chatViewport = document.getElementById('chatViewport');
    const dropzoneOverlay = document.getElementById('dropzoneOverlay');
    const messagesContainer = document.getElementById('messagesContainer');
    const messageInput = document.getElementById('messageInput');
    const btnSend = document.getElementById('btnSend');
    const sendBtnLabel = document.getElementById('sendBtnLabel');
    const sendBtnIcon = document.getElementById('sendBtnIcon');

    const fileInput = document.getElementById('fileInput');
    const btnAttachFile = document.getElementById('btnAttachFile');
    const attachmentPreviewBar = document.getElementById('attachmentPreviewBar');
    const attachedFileName = document.getElementById('attachedFileName');
    const attachedFileSize = document.getElementById('attachedFileSize');
    const btnRemoveAttachment = document.getElementById('btnRemoveAttachment');

    const searchInput = document.getElementById('searchInput');
    const filterPills = document.querySelectorAll('.filter-pill');
    const btnClearChat = document.getElementById('btnClearChat');
    const btnExportChat = document.getElementById('btnExportChat');

    const btnSound = document.getElementById('btnSound');
    const btnTheme = document.getElementById('btnTheme');
    const btnEmoji = document.getElementById('btnEmoji');
    const emojiPopover = document.getElementById('emojiPopover');
    const presetChips = document.querySelectorAll('.preset-chip');

    // Lightbox Modal Selectors
    const lightboxModal = document.getElementById('lightboxModal');
    const lightboxOverlay = document.getElementById('lightboxOverlay');
    const lightboxClose = document.getElementById('lightboxClose');
    const lightboxImage = document.getElementById('lightboxImage');
    const lightboxTitle = document.getElementById('lightboxTitle');
    const lightboxDownload = document.getElementById('lightboxDownload');

    // ==========================================
    // Web Audio Synthesizer Notifications
    // ==========================================
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

    function playSound(type) {
        if (!soundEnabled) return;
        try {
            if (audioCtx.state === 'suspended') audioCtx.resume();
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.connect(gain);
            gain.connect(audioCtx.destination);

            if (type === 'send') {
                osc.frequency.setValueAtTime(600, audioCtx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(900, audioCtx.currentTime + 0.1);
                gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.1);
                osc.start();
                osc.stop(audioCtx.currentTime + 0.1);
            } else if (type === 'recv') {
                osc.frequency.setValueAtTime(880, audioCtx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(440, audioCtx.currentTime + 0.15);
                gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.15);
                osc.start();
                osc.stop(audioCtx.currentTime + 0.15);
            } else if (type === 'file') {
                osc.frequency.setValueAtTime(400, audioCtx.currentTime);
                osc.frequency.exponentialRampToValueAtTime(1200, audioCtx.currentTime + 0.2);
                gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.2);
                osc.start();
                osc.stop(audioCtx.currentTime + 0.2);
            }
        } catch (e) {}
    }

    // ==========================================
    // Toast Notification System
    // ==========================================
    function showToast(message, type = 'info') {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        let icon = 'fa-info-circle';
        if (type === 'success') icon = 'fa-check-circle';
        if (type === 'error') icon = 'fa-exclamation-triangle';

        toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${escapeHtml(message)}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.innerText = text;
        return div.innerHTML;
    }

    function formatBytes(bytes) {
        if (bytes === 0 || !bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    // ==========================================
    // Server-Sent Events (SSE) Realtime Stream
    // ==========================================
    function initSSE() {
        if (eventSource) eventSource.close();
        eventSource = new EventSource('/api/stream');

        eventSource.addEventListener('init', (e) => {
            const data = JSON.parse(e.data);
            updateUIState(data.status);
            messagesList = data.history || [];
            renderAllMessages();
        });

        eventSource.addEventListener('status_changed', (e) => {
            const data = JSON.parse(e.data);
            updateUIState(data);
        });

        eventSource.addEventListener('new_message', (e) => {
            const msg = JSON.parse(e.data);
            messagesList.push(msg);
            appendMessage(msg);

            if (msg.type === 'sent') playSound('send');
            else if (msg.type === 'received') playSound('recv');
            else if (msg.type === 'file') playSound('file');
        });

        eventSource.addEventListener('cleared', () => {
            messagesList = [];
            renderAllMessages();
            showToast("Đã xóa lịch sử hiển thị tin nhắn.", "info");
        });

        eventSource.onerror = (err) => {
            console.error("SSE Connection Error:", err);
        };
    }

    // ==========================================
    // UI State Rendering
    // ==========================================
    function updateUIState(stateData) {
        currentState = stateData;

        displayIp.innerText = currentState.host;
        displayPort.innerText = currentState.port;
        displayConnectedAt.innerText = currentState.stats.connected_at || '--:--:--';

        statSent.innerText = currentState.stats.sent_count;
        statRecv.innerText = currentState.stats.recv_count;
        if (statFilesSent) statFilesSent.innerText = currentState.stats.files_sent || 0;
        if (statFilesRecv) statFilesRecv.innerText = currentState.stats.files_recv || 0;

        statBytesSent.innerText = formatBytes(currentState.stats.bytes_sent);
        statBytesRecv.innerText = formatBytes(currentState.stats.bytes_recv);

        statusBadge.className = 'badge';
        if (currentState.connecting) {
            statusBadge.classList.add('badge-connecting');
            statusText.innerText = 'Đang kết nối...';
            btnConnect.className = 'btn btn-connect';
            connectBtnText.innerText = 'Đang kết nối...';
            btnConnect.disabled = true;
        } else if (currentState.connected) {
            statusBadge.classList.add('badge-connected');
            statusText.innerText = 'Đã kết nối';
            btnConnect.className = 'btn btn-connect btn-disconnect';
            connectBtnText.innerText = 'Ngắt kết nối';
            btnConnect.disabled = false;
        } else {
            statusBadge.classList.add('badge-disconnected');
            statusText.innerText = 'Chưa kết nối';
            btnConnect.className = 'btn btn-connect';
            connectBtnText.innerText = 'Kết nối';
            btnConnect.disabled = false;
        }

        if (currentState.local_server_active) {
            btnLocalServer.classList.add('active');
            localServerText.innerText = 'Local Server: BẬT (9000)';
        } else {
            btnLocalServer.classList.remove('active');
            localServerText.innerText = 'Local Server: TẮT';
        }
    }

    // ==========================================
    // Render Chat & Rich File Messages
    // ==========================================
    function renderAllMessages() {
        messagesContainer.innerHTML = '';
        if (messagesList.length === 0) {
            messagesContainer.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon"><i class="fa-solid fa-comments"></i></div>
                    <h2>TCP Socket Terminal Pro</h2>
                    <p>Hệ thống truyền nhận Tin nhắn & Tập tin xem trước hình ảnh thời gian thực.</p>
                    <div class="welcome-features">
                        <div class="feature-chip"><i class="fa-regular fa-image"></i> Previews Ảnh PNG/JPG</div>
                        <div class="feature-chip"><i class="fa-solid fa-file-code"></i> Text & Code Highlight</div>
                        <div class="feature-chip"><i class="fa-solid fa-paperclip"></i> Drag & Drop File Upload</div>
                        <div class="feature-chip"><i class="fa-solid fa-bolt"></i> SSE Event Streaming</div>
                    </div>
                </div>
            `;
            return;
        }

        messagesList.forEach(msg => appendMessage(msg, false));
        scrollToBottom();
    }

    function appendMessage(msg, autoScroll = true) {
        const welcomeEl = messagesContainer.querySelector('.welcome-message');
        if (welcomeEl) welcomeEl.remove();

        const wrapper = document.createElement('div');
        
        // Match message sender class for bubble positioning
        let isSelf = msg.sender && (msg.sender.includes("Bạn") || msg.sender.includes("Web Client"));
        let bubbleClass = isSelf ? 'sent' : (msg.type === 'file' ? 'received' : msg.type);
        if (msg.type === 'system' || msg.type === 'error') bubbleClass = msg.type;

        wrapper.className = `msg-wrapper ${bubbleClass}`;
        wrapper.dataset.id = msg.id;
        wrapper.dataset.type = msg.type;
        wrapper.dataset.content = (msg.content || '').toLowerCase();

        let icon = 'fa-user';
        if (msg.type === 'received') icon = 'fa-server';
        if (msg.type === 'file') icon = 'fa-file-lines';
        if (msg.type === 'system') icon = 'fa-gear';
        if (msg.type === 'error') icon = 'fa-circle-exclamation';

        let innerBodyHtml = '';

        if (msg.type === 'file') {
            // Render Rich File Card
            if (msg.is_image) {
                innerBodyHtml = `
                    <div class="msg-bubble msg-card-image">
                        <div class="image-preview-container" data-img-url="${msg.file_url}" data-img-name="${msg.file_name}">
                            <img src="${msg.file_url}" alt="${msg.file_name}" loading="lazy">
                            <div class="image-overlay-info">
                                <span>${msg.file_name}</span>
                                <span>${formatBytes(msg.file_size)}</span>
                            </div>
                        </div>
                    </div>
                `;
            } else if (msg.is_text) {
                innerBodyHtml = `
                    <div class="msg-bubble">
                        <div class="file-card">
                            <div class="file-card-icon"><i class="fa-solid fa-file-code"></i></div>
                            <div class="file-card-details">
                                <span class="file-card-name">${msg.file_name}</span>
                                <span class="file-card-size">${formatBytes(msg.file_size)}</span>
                            </div>
                            <a href="${msg.file_url}" download class="btn-download-file">
                                <i class="fa-solid fa-download"></i> Tải về
                            </a>
                        </div>
                        ${msg.preview_text ? `<div class="code-preview-container">${escapeHtml(msg.preview_text)}</div>` : ''}
                    </div>
                `;
            } else {
                innerBodyHtml = `
                    <div class="msg-bubble">
                        <div class="file-card">
                            <div class="file-card-icon"><i class="fa-solid fa-file"></i></div>
                            <div class="file-card-details">
                                <span class="file-card-name">${msg.file_name}</span>
                                <span class="file-card-size">${formatBytes(msg.file_size)}</span>
                            </div>
                            <a href="${msg.file_url}" download class="btn-download-file">
                                <i class="fa-solid fa-download"></i> Tải về
                            </a>
                        </div>
                    </div>
                `;
            }
        } else {
            // Standard Text Message
            innerBodyHtml = `
                <div class="msg-bubble">
                    <div class="msg-content">${escapeHtml(msg.content)}</div>
                    ${(msg.type === 'sent' || msg.type === 'received') ? `
                    <div class="msg-actions">
                        <button class="btn-copy-msg" title="Sao chép">
                            <i class="fa-regular fa-copy"></i>
                        </button>
                    </div>` : ''}
                </div>
            `;
        }

        wrapper.innerHTML = `
            <div class="msg-meta">
                <i class="fa-solid ${icon}"></i>
                <span>${escapeHtml(msg.sender)}</span> •
                <span>${msg.timestamp}</span>
            </div>
            ${innerBodyHtml}
        `;

        // Image Lightbox Click Handler
        const imgContainer = wrapper.querySelector('.image-preview-container');
        if (imgContainer) {
            imgContainer.addEventListener('click', () => {
                const url = imgContainer.dataset.imgUrl;
                const name = imgContainer.dataset.imgName;
                openLightbox(url, name);
            });
        }

        // Copy Text Handler
        const copyBtn = wrapper.querySelector('.btn-copy-msg');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(msg.content);
                showToast("Đã sao chép tin nhắn vào khay nhớ tạm!", "success");
            });
        }

        messagesContainer.appendChild(wrapper);
        applyFilterAndSearchToMessage(wrapper);

        if (autoScroll) scrollToBottom();
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function applyFilterAndSearchToMessage(wrapper) {
        const type = wrapper.dataset.type;
        const content = wrapper.dataset.content;
        const searchVal = searchInput.value.toLowerCase().trim();

        let matchesFilter = (activeFilter === 'all') || 
                            (activeFilter === 'msg' && (type === 'sent' || type === 'received')) ||
                            (activeFilter === 'file' && type === 'file') ||
                            (activeFilter === 'system' && (type === 'system' || type === 'error'));

        let matchesSearch = !searchVal || content.includes(searchVal);

        wrapper.style.display = (matchesFilter && matchesSearch) ? 'flex' : 'none';
    }

    function filterMessages() {
        const wrappers = messagesContainer.querySelectorAll('.msg-wrapper');
        wrappers.forEach(w => applyFilterAndSearchToMessage(w));
    }

    // ==========================================
    // Lightbox Image Viewer Handlers
    // ==========================================
    function openLightbox(url, title) {
        lightboxImage.src = url;
        lightboxTitle.innerText = title;
        lightboxDownload.href = url;
        lightboxModal.classList.remove('hidden');
    }

    function closeLightbox() {
        lightboxModal.classList.add('hidden');
        lightboxImage.src = '';
    }

    lightboxClose.addEventListener('click', closeLightbox);
    lightboxOverlay.addEventListener('click', closeLightbox);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !lightboxModal.classList.contains('hidden')) closeLightbox();
    });

    // ==========================================
    // File Attachment & Drag Drop Handlers
    // ==========================================
    function setAttachedFile(file) {
        selectedFile = file;
        if (file) {
            attachedFileName.innerText = file.name;
            attachedFileSize.innerText = formatBytes(file.size);
            attachmentPreviewBar.classList.remove('hidden');
            sendBtnLabel.innerText = 'Gửi File';
            sendBtnIcon.className = 'fa-solid fa-cloud-arrow-up';
        } else {
            attachmentPreviewBar.classList.add('hidden');
            sendBtnLabel.innerText = 'Gửi';
            sendBtnIcon.className = 'fa-solid fa-paper-plane';
            fileInput.value = '';
        }
    }

    btnAttachFile.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            setAttachedFile(e.target.files[0]);
        }
    });

    btnRemoveAttachment.addEventListener('click', () => setAttachedFile(null));

    // Drag and Drop Zone Events
    ['dragenter', 'dragover'].forEach(eventName => {
        chatViewport.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzoneOverlay.classList.remove('hidden');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        chatViewport.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (eventName === 'drop') {
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    setAttachedFile(files[0]);
                    showToast(`Đã chọn tập tin: ${files[0].name}`, "info");
                }
            }
            dropzoneOverlay.classList.add('hidden');
        }, false);
    });

    // ==========================================
    // Send Message / Send File Action
    // ==========================================
    async function handleSend() {
        if (!currentState.connected) {
            showToast("Bạn chưa kết nối tới TCP Server!", "error");
            return;
        }

        if (selectedFile) {
            // Upload & Send File over TCP Socket
            const fileToUpload = selectedFile;
            setAttachedFile(null); // Clear preview

            const formData = new FormData();
            formData.append('file', fileToUpload);

            try {
                showToast(`Đang truyền tập tin ${fileToUpload.name}...`, "info");
                const res = await fetch('/api/upload_file', {
                    method: 'POST',
                    body: formData
                });
                const json = await res.json();
                if (res.ok) {
                    showToast(json.message, "success");
                } else {
                    showToast(json.message, "error");
                }
            } catch (err) {
                showToast("Lỗi mạng khi truyền tập tin.", "error");
            }
        } else {
            // Send Text Message
            const msgText = messageInput.value.trim();
            if (!msgText) return;

            messageInput.value = '';
            messageInput.style.height = 'auto';

            try {
                const res = await fetch('/api/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: msgText })
                });
                const json = await res.json();
                if (!res.ok) showToast(json.message, "error");
            } catch (err) {
                showToast("Lỗi mạng khi gửi tin nhắn.", "error");
            }
        }
    }

    btnSend.addEventListener('click', handleSend);

    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
    });

    // Connect / Disconnect Toggle
    btnConnect.addEventListener('click', async () => {
        if (currentState.connected) {
            try {
                const res = await fetch('/api/disconnect', { method: 'POST' });
                const json = await res.json();
                showToast(json.message, "info");
            } catch (err) {
                showToast("Không thể gửi yêu cầu ngắt kết nối.", "error");
            }
        } else {
            const host = targetIpInput.value.trim();
            const port = parseInt(targetPortInput.value.trim());

            if (!host || isNaN(port)) {
                showToast("Vui lòng nhập IP và Port hợp lệ!", "error");
                return;
            }

            try {
                const res = await fetch('/api/connect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host, port })
                });
                const json = await res.json();
                if (res.ok) showToast(json.message, "success");
                else showToast(json.message, "error");
            } catch (err) {
                showToast("Lỗi kết nối tới web backend.", "error");
            }
        }
    });

    // Local Server Toggle
    btnLocalServer.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/server/toggle', { method: 'POST' });
            const json = await res.json();
            if (res.ok) showToast(json.message, "success");
            else showToast(json.message, "error");
        } catch (err) {
            showToast("Lỗi thao tác với Local Server.", "error");
        }
    });

    // Preset Chips
    presetChips.forEach(chip => {
        chip.addEventListener('click', () => {
            messageInput.value = chip.dataset.cmd;
            messageInput.focus();
        });
    });

    // Filter Pills
    filterPills.forEach(pill => {
        pill.addEventListener('click', () => {
            filterPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            activeFilter = pill.dataset.filter;
            filterMessages();
        });
    });

    searchInput.addEventListener('input', filterMessages);

    // Clear Chat
    btnClearChat.addEventListener('click', async () => {
        if (confirm("Xóa toàn bộ màn hình hiển thị?")) {
            await fetch('/api/clear', { method: 'POST' });
        }
    });

    // Export Chat Log
    btnExportChat.addEventListener('click', () => {
        if (messagesList.length === 0) {
            showToast("Chưa có tin nhắn nào để xuất!", "info");
            return;
        }
        const textContent = messagesList.map(m => `[${m.timestamp}] [${m.sender}] (${m.type}): ${m.content || m.file_name}`).join('\n');
        const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `TCP_Socket_Chat_Log_${new Date().toISOString().slice(0,10)}.txt`;
        a.click();
        URL.revokeObjectURL(url);
        showToast("Đã xuất nhật ký chat thành công!", "success");
    });

    // Emoji Popover Toggle
    btnEmoji.addEventListener('click', (e) => {
        e.stopPropagation();
        emojiPopover.classList.toggle('hidden');
    });

    document.querySelectorAll('.emoji-item').forEach(emoji => {
        emoji.addEventListener('click', () => {
            messageInput.value += emoji.innerText;
            emojiPopover.classList.add('hidden');
            messageInput.focus();
        });
    });

    document.addEventListener('click', (e) => {
        if (!emojiPopover.contains(e.target) && e.target !== btnEmoji) {
            emojiPopover.classList.add('hidden');
        }
    });

    // Sound & Theme Controls
    btnSound.addEventListener('click', () => {
        soundEnabled = !soundEnabled;
        btnSound.innerHTML = soundEnabled ? '<i class="fa-solid fa-volume-high"></i>' : '<i class="fa-solid fa-volume-xmark"></i>';
        showToast(soundEnabled ? "Đã bật âm thanh" : "Đã tắt âm thanh", "info");
    });

    btnTheme.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', nextTheme);
        btnTheme.innerHTML = nextTheme === 'dark' ? '<i class="fa-solid fa-moon"></i>' : '<i class="fa-solid fa-sun"></i>';
    });

    // Start SSE Stream
    initSSE();
});
