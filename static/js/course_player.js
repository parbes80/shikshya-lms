document.addEventListener('DOMContentLoaded', () => {
  const video = document.getElementById('lesson-video');
  const lessonId = video ? video.getAttribute('data-lesson-id') : null;
  const initialProgress = video ? parseFloat(video.getAttribute('data-start-seconds') || 0) : 0;

  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetPane = btn.getAttribute('data-tab');

      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const pane = document.getElementById(targetPane);
      if (pane) pane.classList.add('active');
    });
  });

  if (video && lessonId) {
    video.addEventListener('loadedmetadata', () => {
      video.currentTime = initialProgress;
    });

    let lastSavedTime = 0;
    video.addEventListener('timeupdate', () => {
      const currentTime = Math.floor(video.currentTime);
      if (currentTime - lastSavedTime >= 5) {
        lastSavedTime = currentTime;
        saveVideoProgress(currentTime, false);
      }
    });

    video.addEventListener('ended', () => {
      saveVideoProgress(Math.floor(video.duration), true);
    });

    function saveVideoProgress(seconds, isCompleted) {
      csrfFetch('/api/progress/video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lesson_id: parseInt(lessonId),
          seconds: seconds,
          is_completed: isCompleted
        })
      })
      .then(res => res.json())
      .then(data => {
        if (data.success && isCompleted) {
          const currentCheck = document.getElementById(`check-${lessonId}`);
          if (currentCheck) {
            currentCheck.className = 'fas fa-check-circle lesson-check-icon completed';
          }

          showToast('Lesson marked as completed! Progress updated.');

          if (data.progress_percent >= 100.0) {
            showToast('Congratulations! Course completed! \U0001f393 Go check your Certificate on the Student Dashboard!');
          }
        }
      })
      .catch(err => console.error('Error tracking video:', err));
    }
  }

  const speedBtn = document.getElementById('speed-btn');
  if (speedBtn && video) {
    speedBtn.addEventListener('change', (e) => {
      video.playbackRate = parseFloat(e.target.value);
    });
  }

  const notesText = document.getElementById('lesson-notes-area');
  if (notesText && lessonId) {
    notesText.value = localStorage.getItem(`notes_${lessonId}`) || '';

    notesText.addEventListener('input', () => {
      localStorage.setItem(`notes_${lessonId}`, notesText.value);
    });
  }

  const formTopic = document.getElementById('new-topic-form');
  const forumContainer = document.getElementById('discussion-container');

  if (formTopic && forumContainer) {
    formTopic.addEventListener('submit', (e) => {
      e.preventDefault();

      const formData = new FormData(formTopic);
      formData.append('csrf_token', getCSRFToken());

      csrfFetch('/api/discussions/create', {
        method: 'POST',
        body: formData
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          showToast('Discussion topic created successfully!');
          formTopic.reset();

          const thread = document.createElement('div');
          thread.className = 'thread-item';
          thread.id = `thread-${data.topic_id}`;
          thread.innerHTML = `
            <div class="thread-header">
              <div class="thread-author"><i class="fas fa-user-circle"></i> ${data.author}</div>
              <div class="thread-time">${data.created_at}</div>
            </div>
            <h4>${data.title}</h4>
            <p style="margin: 0.5rem 0; font-size: 0.9rem;">${formData.get('content')}</p>
            <div class="thread-replies" id="replies-${data.topic_id}"></div>
            <form class="reply-form" data-topic-id="${data.topic_id}" style="margin-top: 1rem; display: flex; gap: 0.5rem;">
              <input type="text" name="content" class="form-control" placeholder="Write a reply..." required>
              <button class="btn btn-primary" style="padding: 0.5rem 1rem;"><i class="fas fa-paper-plane"></i></button>
            </form>
          `;

          forumContainer.insertBefore(thread, forumContainer.firstChild);
          bindReplySubmit(thread.querySelector('.reply-form'));
        }
      })
      .catch(err => console.error('Error posting discussion topic:', err));
    });
  }

  document.querySelectorAll('.reply-form').forEach(bindReplySubmit);

  function bindReplySubmit(form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const topicId = form.getAttribute('data-topic-id');
      const input = form.querySelector('input[name="content"]');
      const repliesBox = document.getElementById(`replies-${topicId}`);

      const formData = new FormData();
      formData.append('content', input.value);
      formData.append('csrf_token', getCSRFToken());

      csrfFetch(`/api/discussions/${topicId}/reply`, {
        method: 'POST',
        body: formData
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          input.value = '';
          const reply = document.createElement('div');
          reply.className = 'reply-item';
          reply.innerHTML = `
            <div class="thread-header" style="margin-bottom: 0.25rem;">
              <div class="thread-author" style="font-size: 0.8rem;"><i class="fas fa-user"></i> ${data.author}</div>
              <div class="thread-time" style="font-size: 0.75rem;">${data.created_at}</div>
            </div>
            <p>${data.content}</p>
          `;
          repliesBox.appendChild(reply);
        }
      })
      .catch(err => console.error('Error replying:', err));
    });
  }

  document.querySelectorAll('.assignment-submit-form').forEach(form => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();

      const assignmentId = form.getAttribute('data-assignment-id');
      const formData = new FormData(form);
      formData.append('csrf_token', getCSRFToken());

      csrfFetch(`/api/assignments/${assignmentId}/submit`, {
        method: 'POST',
        body: formData
      })
      .then(res => res.json())
      .then(data => {
        if (data.success) {
          showToast(data.message || 'Assignment submitted successfully!');
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        } else {
          showToast(data.error || 'Submission failed. Please try again.');
        }
      })
      .catch(err => {
        console.error('Error submitting assignment:', err);
        showToast('An error occurred during submission.');
      });
    });
  });

  function showToast(message) {
    const container = document.querySelector('.flash-container') || document.body;
    const toast = document.createElement('div');
    toast.className = 'alert alert-info';
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.left = '20px';
    toast.style.zIndex = '2000';
    toast.style.animation = 'slideIn 0.3s forwards';
    toast.innerHTML = `
      <span>${message}</span>
      <i class="fas fa-times close-alert" style="cursor: pointer; margin-left: 1rem;"></i>
    `;

    toast.querySelector('.close-alert').addEventListener('click', () => toast.remove());
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
});
