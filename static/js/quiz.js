document.addEventListener('DOMContentLoaded', () => {
  const quizBox = document.getElementById('quiz-box');
  if (!quizBox) return;

  const quizId = quizBox.getAttribute('data-quiz-id');
  const durationMinutes = parseInt(quizBox.getAttribute('data-duration') || 10);

  const questionCards = document.querySelectorAll('.question-card');
  const prevBtn = document.getElementById('prev-question-btn');
  const nextBtn = document.getElementById('next-question-btn');
  const submitBtn = document.getElementById('submit-quiz-btn');
  const timerDisplay = document.getElementById('quiz-timer');
  const progressBar = document.getElementById('quiz-progress-fill');

  let currentIdx = 0;
  let timeRemaining = durationMinutes * 60;
  let submitted = false;

  function disableAllInputs() {
    document.querySelectorAll('.question-card input, .question-card button').forEach(function(el) { el.disabled = true; });
  }

  const timerInterval = setInterval(() => {
    if (submitted) { clearInterval(timerInterval); return; }

    if (timeRemaining <= 0) {
      clearInterval(timerInterval);
      timerDisplay.textContent = "00:00 - TIME EXPIRED";
      timerDisplay.style.color = '#ef4444';
      timerDisplay.style.fontWeight = 'bold';
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
      if (submitBtn) submitBtn.disabled = true;
      disableAllInputs();
      submitQuiz();
      return;
    }

    timeRemaining--;
    const mins = Math.floor(timeRemaining / 60);
    const secs = timeRemaining % 60;
    timerDisplay.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;

    if (timeRemaining < 60) {
      timerDisplay.style.color = '#ef4444';
      timerDisplay.style.animation = 'pulse 1s infinite';
    }
    if (timeRemaining === 30) {
      showToast('30 seconds remaining!');
    }
  }, 1000);

  showQuestion(0);

  if (prevBtn) prevBtn.addEventListener('click', () => navigateQuestion(-1));
  if (nextBtn) nextBtn.addEventListener('click', () => navigateQuestion(1));

  function showQuestion(index) {
    questionCards.forEach((card, idx) => {
      card.style.display = idx === index ? 'block' : 'none';
    });

    currentIdx = index;
    progressBar.style.width = `${((index + 1) / questionCards.length) * 100}%`;

    if (prevBtn) prevBtn.style.visibility = index === 0 ? 'hidden' : 'visible';
    if (nextBtn) {
      if (index === questionCards.length - 1) {
        nextBtn.style.display = 'none';
        if (submitBtn) submitBtn.style.display = 'inline-flex';
      } else {
        nextBtn.style.display = 'inline-flex';
        if (submitBtn) submitBtn.style.display = 'none';
      }
    }
  }

  function navigateQuestion(step) {
    const nextIdx = currentIdx + step;
    if (nextIdx >= 0 && nextIdx < questionCards.length) {
      showQuestion(nextIdx);
    }
  }

  if (submitBtn) {
    submitBtn.addEventListener('click', () => {
      if (confirm('Are you sure you want to submit your quiz?')) {
        clearInterval(timerInterval);
        submitBtn.disabled = true;
        if (prevBtn) prevBtn.disabled = true;
        if (nextBtn) nextBtn.disabled = true;
        disableAllInputs();
        submitted = true;
        submitQuiz();
      }
    });
  }

  function submitQuiz() {
    const answers = {};

    questionCards.forEach(card => {
      const qId = card.getAttribute('data-question-id');
      const checkedInput = card.querySelector('input[type="radio"]:checked');
      if (checkedInput) {
        answers[qId] = checkedInput.value;
      }
    });

    csrfFetch('/api/quiz/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quiz_id: parseInt(quizId),
        answers: answers
      })
    })
    .then(res => res.json())
    .then(data => {
      renderQuizResults(data);
    })
    .catch(err => {
      console.error('Quiz submission failed:', err);
      alert('An error occurred during submission. Please try again.');
    });
  }

  function renderQuizResults(data) {
    const resultsContainer = document.getElementById('quiz-results-container');
    if (!resultsContainer) return;

    quizBox.style.display = 'none';
    resultsContainer.style.display = 'block';

    const finalScore = document.getElementById('quiz-final-score');
    const finalStatus = document.getElementById('quiz-final-status');

    finalScore.textContent = `${round(data.score, 1)}%`;

    if (data.is_passed) {
      finalStatus.textContent = "PASSED \U0001f3c6";
      finalStatus.className = "status-badge passed";
      finalStatus.style.background = 'var(--secondary)';
      finalStatus.style.color = '#fff';
    } else {
      finalStatus.textContent = "FAILED \u274c";
      finalStatus.className = "status-badge failed";
      finalStatus.style.background = '#ef4444';
      finalStatus.style.color = '#fff';
    }

    const reviewList = document.getElementById('quiz-corrections-review');
    reviewList.innerHTML = '';

    questionCards.forEach((card, idx) => {
      const qId = card.getAttribute('data-question-id');
      const qText = card.querySelector('.question-text').textContent;
      const correction = data.results[qId];

      const reviewRow = document.createElement('div');
      reviewRow.className = `review-row ${correction.is_correct ? 'correct' : 'incorrect'}`;
      reviewRow.style.padding = '1rem';
      reviewRow.style.border = '1px solid var(--border-color)';
      reviewRow.style.borderRadius = 'var(--radius-md)';
      reviewRow.style.marginBottom = '1rem';
      reviewRow.style.background = correction.is_correct ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)';

      reviewRow.innerHTML = `
        <h5 style="margin-bottom: 0.5rem;">Q${idx + 1}: ${qText}</h5>
        <p style="font-size: 0.9rem; font-weight: bold;">
          Result: ${correction.is_correct ? '<span style="color: var(--secondary);"><i class="fas fa-check"></i> Correct</span>' : '<span style="color: #ef4444;"><i class="fas fa-times"></i> Wrong</span>'}
        </p>
        <p style="font-size: 0.85rem; margin-top: 0.25rem; color: var(--text-muted);">
          Correct Answer: <strong>${correction.correct_choice_text}</strong>
        </p>
      `;
      reviewList.appendChild(reviewRow);
    });
  }

  function round(val, precision) {
    const factor = Math.pow(10, precision);
    return Math.round(val * factor) / factor;
  }

  function showToast(message) {
    var t = document.createElement('div');
    t.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;font-size:0.8rem;padding:0.5rem 1rem;background:#1e293b;color:#fff;border-radius:8px;animation:fadeIn 0.3s forwards;';
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(function() { t.style.opacity = '0'; setTimeout(function() { t.remove(); }, 300); }, 3000);
  }
});
