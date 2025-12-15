from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, g
)
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.tag import pos_tag
from nltk.probability import FreqDist
from collections import Counter
import random
import re
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'ai-studyhub-2025'

# ---------- NLTK ----------
stop_words = set(stopwords.words('english'))

def extractive_summary(text, num_sents=4):
    sentences = sent_tokenize(text)
    if len(sentences) <= num_sents:
        return ' '.join(sentences)

    words = [
        w.lower() for w in word_tokenize(text)
        if w.isalnum() and w.lower() not in stop_words
    ]
    freq = FreqDist(words)

    scores = {}
    for sent in sentences:
        sent_words = [
            w.lower() for w in word_tokenize(sent)
            if w.isalnum()
        ]
        if not sent_words:
            continue
        score = sum(freq[w] for w in sent_words if w in freq)
        scores[sent] = score / len(sent_words)

    top_sentences = sorted(scores, key=scores.get, reverse=True)[:num_sents]
    return ' '.join(top_sentences)

def generate_quiz(summary, num_questions=6):
    sentences = sent_tokenize(summary)
    if not sentences:
        return []

    words = word_tokenize(summary.lower())
    nouns = [w for w, pos in pos_tag(words) if pos.startswith('NN')]
    nouns = list(set(nouns))

    quiz = []
    used_sentences = set()

    for i in range(num_questions):
        available = [s for s in sentences if s not in used_sentences]
        if not available:
            break

        sent = random.choice(available)
        used_sentences.add(sent)

        q_type = 'mcq' if i < num_questions // 2 else 'short'

        if nouns:
            target = random.choice(nouns)
        else:
            target = 'concept'

        pattern = re.compile(re.escape(target), re.IGNORECASE)
        question_text = pattern.sub('____', sent, count=1).strip()
        ans_clean = target.strip('.,;:!?')

        if q_type == 'mcq':
            distractors = random.sample(
                ['system', 'method', 'data', 'model', 'process', 'example', 'result'],
                k=3
            )
            correct = ans_clean.capitalize()
            options = [correct] + distractors
            random.shuffle(options)
            quiz.append({
                'type': 'mcq',
                'question': question_text,
                'answer': correct,
                'options': options,
                'correct_idx': options.index(correct)
            })
        else:
            quiz.append({
                'type': 'short',
                'question': question_text,
                'answer': ans_clean.lower()
            })

    return quiz


def extract_concepts(summary, top_n=15):
    words = [
        w.lower() for w in word_tokenize(summary)
        if w.isalpha() and w.lower() not in stop_words
    ]
    counts = Counter(words)
    return [{'term': w, 'count': c} for w, c in counts.most_common(top_n)]

# ---------- SQLite ----------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'instance' / 'studyhub.db'
DB_PATH.parent.mkdir(exist_ok=True)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            title TEXT,
            summary TEXT,
            score INTEGER,
            total INTEGER,
            percentage REAL
        );
    """)
    db.commit()

# ---------- Routes: Pages ----------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/summarize-page')
def summarize_page():
    return render_template('summarize.html')

@app.route('/quiz')
def quiz_page():
    summary = session.get('summary', '')
    if not summary:
        return redirect(url_for('summarize_page'))

    quiz_data = generate_quiz(summary)
    if not quiz_data:
        quiz_data = [{
            'type': 'info',
            'question': 'Summary too short to generate quiz. Add more detailed notes.',
            'answer': '',
            'options': [],
            'correct_idx': -1
        }]
    session['quiz'] = quiz_data
    return render_template('quiz.html', quiz=quiz_data)

@app.route('/concepts')
def concepts_page():
    summary = session.get('summary', '')
    concepts = extract_concepts(summary) if summary else []
    return render_template('concepts.html', concepts=concepts, summary=summary)

@app.route('/results')
def results_page():
    stats = session.get('stats')
    if not stats:
        return redirect(url_for('home'))
    return render_template('feedback.html', stats=stats)

@app.route('/history')
def history_page():
    db = get_db()
    rows = db.execute("""
        SELECT id, created_at, title, score, total, percentage
        FROM sessions
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()
    return render_template('history.html', sessions=rows)

# ---------- APIs ----------
@app.route('/summarize', methods=['POST'])
def summarize_api():
    data = request.json or {}
    text = data.get('text', '').strip()
    mode = data.get('mode', 'paragraph')

    if not text:
        return jsonify({'error': 'Please enter text'}), 400

    base_summary = extractive_summary(text)

    if mode == 'bullets':
        sentences = sent_tokenize(base_summary)
        summary = '\n'.join(f"• {s.strip()}" for s in sentences)
    elif mode == 'outline':
        sentences = sent_tokenize(base_summary)
        summary = '\n'.join(f"- {s.strip()}" for s in sentences)
    else:
        summary = base_summary

    session['summary'] = summary
    session['raw_text'] = text

    return jsonify({'summary': summary})

@app.route('/feedback', methods=['POST'])
def feedback_api():
    data = request.json or {}
    answers = data.get('answers', [])
    quiz = session.get('quiz', [])

    score = 0
    per_question = []
    weak_areas = []

    for i, user_ans in enumerate(answers):
        if i >= len(quiz):
            break
        q = quiz[i]
        qtype = q.get('type', 'mcq')

        if qtype == 'mcq':
            is_correct = (user_ans == q['correct_idx'])
        elif qtype == 'short':
            user_text = (user_ans or "").strip().lower()
            is_correct = q['answer'] in user_text and len(user_text) > 0
        else:
            is_correct = False

        if is_correct:
            score += 1
        else:
            weak_areas.append(q.get('answer', 'concept'))
        per_question.append(int(is_correct))

    total = len(per_question) or 1
    percentage = round((score / total) * 100, 1)

    stats = {
        'score': score,
        'total': total,
        'percentage': percentage,
        'per_question': per_question,
        'weak_areas': list(set(weak_areas))[:5]
    }
    session['stats'] = stats

    db = get_db()
    db.execute(
        "INSERT INTO sessions(created_at, title, summary, score, total, percentage) "
        "VALUES(datetime('now'), ?, ?, ?, ?, ?)",
        ('Study Session', session.get('summary', ''), score, total, percentage)
    )
    db.commit()

    return jsonify({'redirect': url_for('results_page')})

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, port=5000)
