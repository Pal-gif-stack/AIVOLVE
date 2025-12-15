async function generateSummary() {
  const text = document.getElementById('inputText').value.trim();
  if (!text) {
    alert('Please paste some text first.');
    return;
  }
  const modeEl = document.querySelector('input[name="mode"]:checked');
  const mode = modeEl ? modeEl.value : 'paragraph';

  const res = await fetch('/summarize', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text, mode})
  });
  const data = await res.json();
  if (data.error) {
    alert(data.error);
    return;
  }

  document.getElementById('summaryOutput').textContent = data.summary;
  document.getElementById('toQuizBtn').style.display = 'inline-block';
}

function goToQuiz() {
  window.location.href = '/quiz';
}

async function submitQuiz() {
  const answers = [];
  const blocks = document.querySelectorAll('.quiz-item');

  blocks.forEach((block, qIndex) => {
    const short = block.querySelector('.short-answer');
    if (short) {
      answers[qIndex] = short.value;
    } else {
      const selected = block.querySelector('input[type="radio"]:checked');
      answers[qIndex] = selected ? parseInt(selected.value) : -1;
    }
  });

  const res = await fetch('/feedback', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({answers})
  });
  const data = await res.json();
  if (data.redirect) {
    window.location.href = data.redirect;
  }
}
