document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('ai-chat-toggle-btn');
  const drawer = document.getElementById('ai-chat-drawer');
  const closeBtn = document.getElementById('ai-chat-close-btn');
  const chatForm = document.getElementById('ai-chat-form');
  const chatInput = document.getElementById('ai-chat-input');
  const chatMessages = document.getElementById('ai-chat-messages');

  if (!toggleBtn || !drawer) return;

  toggleBtn.addEventListener('click', () => {
    drawer.classList.toggle('active');
    if (drawer.classList.contains('active')) {
      chatInput.focus();
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      drawer.classList.remove('active');
    });
  }

  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const query = chatInput.value.trim();
    if (!query) return;

    appendBubble(query, 'user');
    chatInput.value = '';

    const typingIndicator = appendTypingIndicator();
    chatMessages.scrollTop = chatMessages.scrollHeight;

    csrfFetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: query })
    })
    .then(res => res.json())
    .then(data => {
      typingIndicator.remove();
      appendBubble(data.reply, 'bot');
      chatMessages.scrollTop = chatMessages.scrollHeight;
    })
    .catch(err => {
      console.error('AI Connection Error:', err);
      typingIndicator.remove();
      appendBubble('Sorry! I am experiencing network connection issues. Let me try again in a bit.', 'bot');
      chatMessages.scrollTop = chatMessages.scrollHeight;
    });
  });

  function appendBubble(content, sender) {
    const bubble = document.createElement('div');
    bubble.className = `chat-msg ${sender}`;

    if (content.includes('```')) {
      bubble.innerHTML = parseMarkdownCode(content);
    } else {
      bubble.textContent = content;
    }

    chatMessages.appendChild(bubble);
  }

  function appendTypingIndicator() {
    const bubble = document.createElement('div');
    bubble.className = 'chat-msg bot typing-indicator';
    bubble.innerHTML = `
      <span style="animation: pulse 1s infinite alternate; font-style: italic; color: var(--text-muted);">AI is typing...</span>
    `;
    chatMessages.appendChild(bubble);
    return bubble;
  }

  function parseMarkdownCode(text) {
    return text.replace(/```(\w+)?([\s\S]*?)```/g, '<pre style="background: #1e293b; color: #fff; padding: 0.5rem; border-radius: 6px; overflow-x: auto; margin-top: 0.5rem; font-family: monospace;"><code>$2</code></pre>');
  }
});
