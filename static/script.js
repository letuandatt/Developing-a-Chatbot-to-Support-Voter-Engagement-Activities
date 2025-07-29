class ChatGPTClone {
    constructor() {
        this.currentSession = null;
        this.isProcessing = false;
        this.controller = null;
        this.isStreaming = false;
        this.conversationHistory = [];
        this.maxContextMessages = 30;
        this.currentBotMessage = null;
        this.currentDisplayedText = '';
        this.responseStartTime = null; // Thêm tracking thời gian bắt đầu
        this.responseEndTime = null;   // Thêm tracking thời gian kết thúc

        this.initializeElements();
        this.initializeEventListeners();
        this.setupMarkdown();
        this.loadSessions();
        this.updateButtonStates();
    }

    initializeElements() {
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.chatMessages = document.getElementById('chatMessages');
        this.newChatBtn = document.getElementById('newChatBtn');
        this.chatHistory = document.getElementById('chatHistory');
        this.sidebar = document.getElementById('sidebar');
        this.toggleSidebarBtn = document.getElementById('toggleSidebar');
        this.toastContainer = document.getElementById('toastContainer');
        this.stopBtn = document.getElementById('stopBtn')
    }

    initializeEventListeners() {
        // Send message
        this.sendBtn.addEventListener('click', () => this.sendMessage());

        // Input handling
        this.messageInput.addEventListener('input', () => this.handleInputChange());
        this.messageInput.addEventListener('keydown', (e) => this.handleKeydown(e));

        // New chat
        this.newChatBtn.addEventListener('click', () => this.createNewChat());

        // Toggle sidebar (mobile)
        if (this.toggleSidebarBtn) {
            this.toggleSidebarBtn.addEventListener('click', () => this.toggleSidebar());
        }

        // Stop response
        if(this.stopBtn){
            this.stopBtn.addEventListener("click", () => this.stopResponse());
        }

        // Auto-focus
        this.messageInput.focus();


    }

    setupMarkdown() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                highlight: function(code, lang) {
                    if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                        try {
                            return hljs.highlight(code, { language: lang }).value;
                        } catch (err) {}
                    }
                    return code;
                }
            });
        }

        // Initialize highlight.js
        if (typeof hljs !== 'undefined') {
            hljs.configure({ ignoreUnescapedHTML: true });
        }
    }

    // Cập nhật trạng thái hiển thị nút gửi/dừng
    updateButtonStates() {
        const hasContent = this.messageInput.value.trim().length > 0;

        if (this.isStreaming) {
            // Đang streaming: ẩn nút gửi, hiện nút dừng
            this.sendBtn.style.display = 'none';
            this.stopBtn.style.display = 'flex';
        } else {
            // Không streaming: hiện nút gửi, ẩn nút dừng
            this.sendBtn.style.display = 'flex';
            this.stopBtn.style.display = 'none';

            // Disable nút gửi nếu không có nội dung hoặc đang xử lý
            this.sendBtn.disabled = !hasContent || this.isProcessing;
            this.sendBtn.classList.toggle('active', hasContent && !this.isProcessing);
        }
    }

    handleInputChange() {
        const hasContent = this.messageInput.value.trim().length > 0;
        this.sendBtn.classList.toggle('active', hasContent);

        // Auto-resize
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 200) + 'px';
    }

    handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this.sendMessage();
        }
    }

    async loadSessions() {
        try {
            const response = await fetch('/api/sessions');
            const sessions = await response.json();

            this.chatHistory.innerHTML = '';

            sessions.forEach(session => {
                const sessionElement = this.createSessionElement(session);
                this.chatHistory.appendChild(sessionElement);
            });

        } catch (error) {
            console.error('Error loading sessions:', error);
        }
    }

    createSessionElement(session) {
        const div = document.createElement('div');
        div.className = 'history-item';
        div.dataset.sessionId = session.id;

        div.innerHTML = `
            <i class="fas fa-message"></i>
            <span>${session.title}</span>
            <button class="delete-btn" title="Delete chat">
                <i class="fas fa-trash"></i>
            </button>
        `;

        // Click to open session
        div.addEventListener('click', (e) => {
            if (!e.target.closest('.delete-btn')) {
                this.openSession(session.id);
            }
        });

        // Delete session
        const deleteBtn = div.querySelector('.delete-btn');
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.deleteSession(session.id);
        });

        return div;
    }

    async openSession(sessionId) {
        try {
            // Update active session
            document.querySelectorAll('.history-item').forEach(item => {
                item.classList.remove('active');
            });

            const sessionElement = document.querySelector(`[data-session-id="${sessionId}"]`);
            if (sessionElement) {
                sessionElement.classList.add('active');
            }

            this.currentSession = sessionId;

            // Load messages
            const response = await fetch(`/api/messages/${sessionId}`);
            const messages = await response.json();

            // Clear current messages
            this.chatMessages.innerHTML = '';
            this.conversationHistory = [];

            // Load messages
            messages.forEach(message => {
                this.addMessage(message.content, message.role, false);
                this.conversationHistory.push({
                    role: message.role,
                    content: message.content
                })
            });

            this.trimConversationHistory();

            messages.forEach(message => {
            const messageElement = this.addMessage(message.content, message.role, false);

            // Thêm response time nếu có (cho tin nhắn bot)
            if (message.role === 'bot' && message.response_time) {
                this.addResponseTimeToExistingMessage(messageElement, message.response_time);
            }
        });

            this.scrollToBottom();

        } catch (error) {
            console.error('Error opening session:', error);
            this.showToast('Error loading chat session', 'error');
        }
    }

    addResponseTimeToExistingMessage(messageElement, responseTimeMs) {
        const responseTimeElement = document.createElement('div');
        responseTimeElement.className = 'response-time';
        responseTimeElement.innerHTML = `
            <i class="fas fa-clock"></i>
            <span>Phản hồi trong ${this.formatResponseTime(responseTimeMs)}</span>
        `;

        messageElement.appendChild(responseTimeElement);
    }

    async createNewChat() {
        try {
            const response = await fetch('/api/new_chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            // Clear current chat
            this.chatMessages.innerHTML = '';
            this.conversationHistory = [];

            // Add welcome message
            this.addWelcomeMessage();

            // Set current session
            this.currentSession = data.session_id;

            // Reload sessions list
            await this.loadSessions();

            // Open the new session
            this.openSession(data.session_id);

        } catch (error) {
            console.error('Error creating new chat:', error);
            this.showToast('Error creating new chat', 'error');
        }
    }

    trimConversationHistory() {
        if (this.conversationHistory.length > this.maxContextMessages) {
            this.conversationHistory = this.conversationHistory.slice(-this.maxContextMessages);
        }
    }

    async deleteSession(sessionId) {
        if (!confirm('Are you sure you want to delete this chat?')) {
            return;
        }

        try {
            const response = await fetch(`/api/delete_session/${sessionId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                // If this was the current session, clear it
                if (this.currentSession === sessionId) {
                    this.currentSession = null;
                    this.chatMessages.innerHTML = '';
                    this.addWelcomeMessage();
                }

                // Reload sessions
                await this.loadSessions();

                this.showToast('Chat deleted successfully', 'success');
            } else {
                throw new Error('Failed to delete session');
            }

        } catch (error) {
            console.error('Error deleting session:', error);
            this.showToast('Error deleting chat', 'error');
        }
    }

    addWelcomeMessage() {
        const welcomeDiv = document.createElement('div');
        welcomeDiv.className = 'message-wrapper';

        welcomeDiv.innerHTML = `
            <div class="message bot-message">
                <div class="message-avatar">
                    <div class="avatar-circle bot">
                        <i class="fas fa-robot"></i>
                    </div>
                </div>
                <div class="message-content">
                    <div class="message-text">
                        Xin chào! Tôi là AI assistant với khả năng RAG hybrid. Tôi có thể:
                        
                        • Trả lời từ knowledge base riêng
                        • Tìm kiếm thông tin tổng quát  
                        • Kết hợp nhiều nguồn thông tin
                        • Trò chuyện tự nhiên
                        
                        Hãy hỏi tôi bất cứ điều gì!
                    </div>
                    <div class="message-actions">
                        <button class="action-btn copy-btn" title="Copy">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;

        this.chatMessages.appendChild(welcomeDiv);
    }

    async sendMessage() {
        if (this.controller) {
            this.controller.abort();
        }

        if (this.isProcessing || !this.currentSession) {
            if (!this.currentSession) {
                await this.createNewChat();
            }
            return;
        }

        const message = this.messageInput.value.trim();
        if (!message) return;

        this.isProcessing = true;
        this.isStreaming = true;

        this.updateButtonStates();

        // Add user message
        this.addMessage(message, 'user');

        this.conversationHistory.push({
            role: 'user',
            content: message
        })

        this.trimConversationHistory();

        // Clear input
        this.messageInput.value = '';
        this.handleInputChange();

        // Show typing indicator
        this.showTypingIndicator();

        this.controller = new AbortController();
        const signal = this.controller.signal;

        this.responseStartTime = Date.now();

        try {
            const response = await fetch(`/api/chat/${this.currentSession}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    conversation_history: this.conversationHistory
                }),
                signal: signal
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            // Remove typing indicator
            this.hideTypingIndicator();

            if (data.success) {
                this.currentBotMessage = null;
                this.currentDisplayedText = '';
                await this.addMessageWithStreaming(data.bot_response, 'bot', data.sources);

                this.responseEndTime = Date.now();
                const responseTime = this.responseEndTime - this.responseStartTime;

                this.addResponseTime(responseTime);

                if (this.isStreaming) {
                    this.conversationHistory.push({
                        role: 'bot',
                        content: data.bot_response
                    })

                    this.trimConversationHistory();
                }

                // Reload sessions to update titles
                await this.loadSessions();
            } else {
                this.showError(data.error || 'Có lỗi xảy ra');
            }

        } catch (error) {
            this.hideTypingIndicator();

            if (error.name === 'AbortError') {
                this.showToast('Đã dừng phản hồi.', 'info');

                if (this.conversationHistory.length > 0 &&
                    this.conversationHistory[this.conversationHistory.length - 1].role === 'user') {
                    this.conversationHistory.pop();
                }
            } else {
                console.error('Lỗi khi gọi API:', error);
                this.showError(`Lỗi kết nối: ${error.message}`);
                if (this.conversationHistory.length > 0 &&
                    this.conversationHistory[this.conversationHistory.length - 1].role === 'user') {
                    this.conversationHistory.pop();
                }
            }
        } finally {
            this.isProcessing = false;
            this.isStreaming = false;
            this.controller = null;

            // Cập nhật lại trạng thái nút
            this.updateButtonStates();
            this.messageInput.focus();
        }
    }

    // THÊM PHƯƠNG THỨC MỚI: Hiển thị thời gian phản hồi
    addResponseTime(responseTimeMs) {
        // Tìm tin nhắn bot cuối cùng
        const messageWrappers = this.chatMessages.querySelectorAll('.message-wrapper');
        const lastWrapper = messageWrappers[messageWrappers.length - 1];

        if (lastWrapper && lastWrapper.querySelector('.bot-message')) {
            const botMessage = lastWrapper.querySelector('.bot-message');

            // Tạo element hiển thị thời gian phản hồi
            const responseTimeElement = document.createElement('div');
            responseTimeElement.className = 'response-time';
            responseTimeElement.innerHTML = `
                <i class="fas fa-clock"></i>
                <span>Phản hồi trong ${this.formatResponseTime(responseTimeMs)}</span>
            `;

            // Thêm vào cuối tin nhắn bot
            botMessage.appendChild(responseTimeElement);
        }
    }

    // Format thời gian phản hồi thành dạng dễ đọc
    formatResponseTime(ms) {
        if (ms < 1000) {
            return `${Math.round(ms)}ms`;
        } else if (ms < 60000) {
            return `${(ms / 1000).toFixed(1)}s`;
        } else {
            const minutes = Math.floor(ms / 60000);
            const seconds = Math.floor((ms % 60000) / 1000);
            return `${minutes}m ${seconds}s`;
        }
    }

    stopResponse() {
        if (this.controller) {
            this.controller.abort();
            this.controller = null;
        }

        this.isStreaming = false;
        this.isProcessing = false;
        this.hideTypingIndicator();

        if (this.currentDisplayedText && this.currentDisplayedText.trim()) {
            this.conversationHistory.push({
                role: 'bot',
                content: this.currentDisplayedText.trim()
            });
            this.trimConversationHistory();
        }

        // Cập nhật trạng thái nút
        this.updateButtonStates();

        this.showToast('Đã dừng phản hồi', 'info');
        this.messageInput.focus();
    }

    addMessage(content, type, streaming = true) {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper';

        const message = document.createElement('div');
        message.className = `message ${type}-message`;

        const avatarType = type === 'user' ? 'user' : 'bot';
        const avatarIcon = type === 'user' ? 'fas fa-user' : 'fas fa-robot';

        let messageContent;
        if (type === 'user') {
            messageContent = this.escapeHtml(content);
        } else {
            messageContent = this.renderMarkdown(content);
        }

        message.innerHTML = `
            <div class="message-avatar">
                <div class="avatar-circle ${avatarType}">
                    <i class="${avatarIcon}"></i>
                </div>
            </div>
            <div class="message-content">
                <div class="message-text">${messageContent}</div>
                <div class="message-actions">
                    <button class="action-btn copy-btn" title="Copy">
                        <i class="fas fa-copy"></i>
                    </button>
                </div>
            </div>
        `;

        wrapper.appendChild(message);
        this.chatMessages.appendChild(wrapper);

        // Add copy functionality
        const copyBtn = message.querySelector('.copy-btn');
        copyBtn.addEventListener('click', () => this.copyMessage(content));

        // Add code copy buttons
        this.enhanceCodeBlocks(message);

        // Highlight code
        if (type === 'bot' && typeof hljs !== 'undefined') {
            message.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
        }

        this.scrollToBottom();
        return message;
    }

    async addMessageWithStreaming(content, type, sources = null) {
        const message = this.addMessage('', type, false);
        const textElement = message.querySelector('.message-text');

        this.currentBotMessage = message;
        this.currentDisplayedText = '';

        // Streaming effect
        const words = content.split(' ');

        for (let i = 0; i < words.length; i++) {
            if (!this.isStreaming) {
                break;
            }

            this.currentDisplayedText += words[i] + ' ';
            textElement.innerHTML = this.renderMarkdown(this.currentDisplayedText);

            // Highlight code blocks
            if (typeof hljs !== 'undefined') {
                textElement.querySelectorAll('pre code').forEach(block => {
                    hljs.highlightElement(block);
                });
            }

            this.scrollToBottom();
            await new Promise(resolve => setTimeout(resolve, 20));
        }

        // Final enhancement
        this.enhanceCodeBlocks(message);
    }

    hasIncompleteResponse() {
        if (this.conversationHistory.length < 2) return false;

        const lastBot = this.conversationHistory[this.conversationHistory.length - 1];
        const lastUser = this.conversationHistory[this.conversationHistory.length - 2];

        // Kiểm tra nếu tin nhắn bot cuối cùng có vẻ chưa hoàn thành
        return lastBot && lastBot.role === 'bot' &&
               lastUser && lastUser.role === 'user' &&
               (lastBot.content.length < 100 || // Quá ngắn
                !lastBot.content.trim().endsWith('.') && // Không kết thúc bằng dấu chấm
                !lastBot.content.trim().endsWith('!') && // Không kết thúc bằng dấu chấm than
                !lastBot.content.trim().endsWith('?')); // Không kết thúc bằng dấu hỏi
    }

    renderMarkdown(text) {
        try {
            if (typeof marked !== 'undefined') {
                let html = marked.parse(text);

                if (typeof DOMPurify !== 'undefined') {
                    html = DOMPurify.sanitize(html);
                }

                return html;
            }
            return this.escapeHtml(text);
        } catch (error) {
            console.error('Markdown render error:', error);
            return this.escapeHtml(text);
        }
    }

    enhanceCodeBlocks(messageElement) {
        messageElement.querySelectorAll('pre').forEach(pre => {
            if (pre.querySelector('.code-copy')) return;

            const copyBtn = document.createElement('button');
            copyBtn.className = 'code-copy';
            copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
            copyBtn.onclick = () => {
                const code = pre.querySelector('code');
                navigator.clipboard.writeText(code.textContent);
                copyBtn.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => {
                    copyBtn.innerHTML = '<i class="fas fa-copy"></i>';
                }, 2000);
            };

            pre.appendChild(copyBtn);
        });
    }

    showTypingIndicator() {
        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper';
        wrapper.id = 'typingIndicator';

        wrapper.innerHTML = `
            <div class="typing-indicator">
                <div class="message-avatar">
                    <div class="avatar-circle bot">
                        <i class="fas fa-robot"></i>
                    </div>
                </div>
                <div class="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;

        this.chatMessages.appendChild(wrapper);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typingIndicator');
        if (indicator) {
            indicator.remove();
        }
    }

    copyMessage(text) {
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('Copied to clipboard!', 'success');
        });
    }

    toggleSidebar() {
        this.sidebar.classList.toggle('open');
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');

        const bgClass = {
            'success': 'bg-success',
            'error': 'bg-danger',
            'warning': 'bg-warning',
            'info': 'bg-info'
        }[type] || 'bg-info';

        toast.className = `toast align-items-center text-white ${bgClass} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        this.toastContainer.appendChild(toast);

        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        toast.addEventListener('hidden.bs.toast', () => toast.remove());
    }

    showError(message) {
        this.showToast(message, 'error');
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ChatGPTClone();
});
