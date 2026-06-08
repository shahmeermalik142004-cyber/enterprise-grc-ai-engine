// ==========================================
// CONFIGURATION
// ==========================================
// Point to our local Python proxy!
const API_URL = "http://localhost:8000"; 
// ==========================================

const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const chatHistory = document.getElementById('chat-history');

// Auto-resize textarea
userInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight < 200 ? this.scrollHeight : 200) + 'px';

    if (this.value.trim() !== '') {
        sendBtn.removeAttribute('disabled');
    } else {
        sendBtn.setAttribute('disabled', 'true');
    }
});

// Handle Enter to submit (Shift+Enter for new line)
userInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (this.value.trim() !== '') {
            chatForm.dispatchEvent(new Event('submit'));
        }
    }
});

// Simple markdown renderer for AI responses
function renderMarkdown(text) {
    return text
        // Bold: **text** -> <strong>text</strong>
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // Newlines to <br>
        .replace(/\n/g, '<br>')
        // Bullet points: lines starting with - or •
        .replace(/(<br>|^)\s*[-•]\s+(.*?)(?=<br>|$)/g, '$1&nbsp;&nbsp;• $2');
}

function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}-message`;

    const avatar = document.createElement('div');
    avatar.className = `avatar ${sender}-avatar`;
    avatar.textContent = sender === 'user' ? 'YOU' : 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    if (sender === 'ai') {
        bubble.innerHTML = renderMarkdown(text);
    } else {
        bubble.textContent = text;
    }

    msgDiv.appendChild(sender === 'user' ? bubble : avatar);
    msgDiv.appendChild(sender === 'user' ? avatar : bubble);

    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    return bubble;
}

function showTypingIndicator() {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ai-message typing-container`;
    msgDiv.id = 'typing-indicator';

    const avatar = document.createElement('div');
    avatar.className = `avatar ai-avatar`;
    avatar.textContent = 'AI';

    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(indicator);

    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const message = userInput.value.trim();
    if (!message) return;

    // Disable inputs
    userInput.value = '';
    userInput.style.height = 'auto';
    sendBtn.setAttribute('disabled', 'true');
    userInput.setAttribute('disabled', 'true');

    // Add user message to UI
    addMessage(message, 'user');

    // Show AI is thinking
    showTypingIndicator();

    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // This is CRITICAL to bypass localtunnel's security screen
                'Bypass-Tunnel-Reminder': 'true'
            },
            body: JSON.stringify({ message: message })
        });
        
        removeTypingIndicator();
        
        if (!response.ok) {
            const errBody = await response.text();
            throw new Error(`API Error: ${response.status} - ${errBody}`);
        }
        
        const data = await response.json();
        addMessage(data.reply, 'ai');
        
    } catch (error) {
        removeTypingIndicator();
        addMessage(`🚨 Error connecting to the Kaggle AI Engine.\n\nMake sure the Kaggle notebook is running, and that you pasted the correct URL into the script.js file!\n\nDetails: ${error.message}`, 'ai');
    } finally {
        // Re-enable inputs
        userInput.removeAttribute('disabled');
        userInput.focus();
    }
});

// File Upload Handling
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const uploadText = document.getElementById('upload-text');

uploadZone.addEventListener('click', () => fileInput.click());

uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});

uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});

uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        handleFile(e.target.files[0]);
    }
});

async function handleFile(file) {
    addMessage(`📄 Uploading document: ${file.name}`, 'user');
    showTypingIndicator();
    uploadZone.classList.add('uploading');
    uploadText.textContent = 'Uploading...';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });

        removeTypingIndicator();

        if (!response.ok) {
            const errBody = await response.text();
            throw new Error(`API Error: ${response.status} - ${errBody}`);
        }

        const data = await response.json();
        addMessage(data.reply, 'ai');
    } catch (error) {
        removeTypingIndicator();
        addMessage(`🚨 Error uploading document: ${error.message}`, 'ai');
    } finally {
        uploadZone.classList.remove('uploading');
        uploadText.textContent = 'Upload a policy document (PDF, DOCX, TXT)';
        fileInput.value = '';
    }
}
