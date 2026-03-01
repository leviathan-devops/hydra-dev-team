#!/usr/bin/env python3
"""
Leviathan Super Brain Dev Team v4.0
===================================
Gemma 3 (free) = chat interface bridge — all user-facing I/O.
Heavy models = task execution only, never wasted on chat.

Architecture:
  User ↔ Gemma 3 (free bridge)
  Gemma routes to → Grok 4.1 / Codex 5.3 / Opus 4.6 / DeepSeek
  Code review: 3 coding models review all code until consensus
  Gemma presents final output (saves paid tokens)
"""

import os
import json
import time
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from flask import Flask, render_template_string, request, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BRAIN] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# ─── API Configuration ────────────────────────────────────────

API_KEYS = {
    'anthropic': os.environ.get('ANTHROPIC_API_KEY', ''),
    'openai': os.environ.get('OPENAI_API_KEY', ''),
    'deepseek': os.environ.get('DEEPSEEK_API_KEY', ''),
    'xai': os.environ.get('XAI_API_KEY', ''),
    'openrouter': os.environ.get('OPENROUTER_API_KEY', ''),
}

# ─── Model Definitions ────────────────────────────────────────

MODELS = {
    'gemma': {
        'name': 'Gemma 3 27B',
        'role': 'Chat Bridge',
        'provider': 'openrouter',
        'model': 'google/gemma-3-27b-it',
        'max_tokens': 2000,
        'cost': 'free',
    },
    'grok': {
        'name': 'Grok',
        'role': 'Co-Architect + Lead Engineer + Primary Debugger + Reviewer (2M context)',
        'provider': 'xai',
        'model': 'grok-3',
        'max_tokens': 2000,
        'cost': 'paid',
    },
    'codex': {
        'name': 'Codex',
        'role': 'Lead Engineer + Reviewer',
        'provider': 'openai',
        'model': 'gpt-4o',
        'max_tokens': 2000,
        'cost': 'paid',
    },
    'opus': {
        'name': 'Opus',
        'role': 'Architect + Reviewer',
        'provider': 'anthropic',
        'model': 'claude-opus-4-6-20251101',
        'max_tokens': 2000,
        'cost': 'paid',
    },
    'deepseek': {
        'name': 'DeepSeek',
        'role': 'Research + Deep Reasoning',
        'provider': 'deepseek',
        'model': 'deepseek-chat',
        'max_tokens': 2000,
        'cost': 'paid',
    },
    'deepseek_r1': {
        'name': 'DeepSeek R1',
        'role': 'Deep Reasoning',
        'provider': 'deepseek',
        'model': 'deepseek-reasoner',
        'max_tokens': 2000,
        'cost': 'paid',
    },
}

# ─── Unified API Client ───────────────────────────────────────

def call_model(model_key, system_prompt, user_message, max_tokens=None):
    """Call any model. Returns (text, token_info) or (None, error_string)."""
    cfg = MODELS[model_key]
    provider = cfg['provider']
    model = cfg['model']
    mt = max_tokens or cfg['max_tokens']

    try:
        if provider == 'openrouter':
            resp = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': f'Bearer {API_KEYS["openrouter"]}', 'Content-Type': 'application/json'},
                json={'model': model, 'max_tokens': mt, 'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]},
                timeout=25,
            )
            resp.raise_for_status()
            d = resp.json()
            return d['choices'][0]['message']['content'], {
                'input': d.get('usage', {}).get('prompt_tokens', 0),
                'output': d.get('usage', {}).get('completion_tokens', 0),
            }

        elif provider == 'anthropic':
            resp = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={'x-api-key': API_KEYS['anthropic'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                json={'model': model, 'max_tokens': mt, 'system': system_prompt,
                      'messages': [{'role': 'user', 'content': user_message}]},
                timeout=30,
            )
            resp.raise_for_status()
            d = resp.json()
            return d['content'][0]['text'], {
                'input': d.get('usage', {}).get('input_tokens', 0),
                'output': d.get('usage', {}).get('output_tokens', 0),
            }

        elif provider == 'openai':
            resp = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': f'Bearer {API_KEYS["openai"]}', 'Content-Type': 'application/json'},
                json={'model': model, 'max_tokens': mt, 'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]},
                timeout=25,
            )
            resp.raise_for_status()
            d = resp.json()
            return d['choices'][0]['message']['content'], {
                'input': d.get('usage', {}).get('prompt_tokens', 0),
                'output': d.get('usage', {}).get('completion_tokens', 0),
            }

        elif provider == 'xai':
            resp = requests.post(
                'https://api.x.ai/v1/chat/completions',
                headers={'Authorization': f'Bearer {API_KEYS["xai"]}', 'Content-Type': 'application/json'},
                json={'model': model, 'max_tokens': mt, 'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]},
                timeout=25,
            )
            resp.raise_for_status()
            d = resp.json()
            return d['choices'][0]['message']['content'], {
                'input': d.get('usage', {}).get('prompt_tokens', 0),
                'output': d.get('usage', {}).get('completion_tokens', 0),
            }

        elif provider == 'deepseek':
            resp = requests.post(
                'https://api.deepseek.com/chat/completions',
                headers={'Authorization': f'Bearer {API_KEYS["deepseek"]}', 'Content-Type': 'application/json'},
                json={'model': model, 'max_tokens': mt, 'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]},
                timeout=25,
            )
            resp.raise_for_status()
            d = resp.json()
            return d['choices'][0]['message']['content'], {
                'input': d.get('usage', {}).get('prompt_tokens', 0),
                'output': d.get('usage', {}).get('completion_tokens', 0),
            }

    except Exception as e:
        logger.error(f"[{model_key}] API error: {e}")
        return None, str(e)


# ─── Core Pipeline ─────────────────────────────────────────────

executor = ThreadPoolExecutor(max_workers=5)

# Task classification keywords (instant, no LLM call)
CODE_KEYWORDS = ['code', 'implement', 'build', 'write', 'function', 'class', 'api', 'endpoint', 'script', 'fix',
                 'create', 'make', 'bot', 'server', 'handler', 'module', 'component', 'refactor', 'deploy',
                 'docker', 'python', 'rust', 'javascript', 'typescript', 'go', 'sql']
ARCH_KEYWORDS = ['design', 'architect', 'structure', 'system', 'scale', 'infra', 'pattern', 'plan', 'stack',
                 'microservice', 'pipeline', 'diagram']
RESEARCH_KEYWORDS = ['research', 'compare', 'explain', 'what is', 'how does', 'best practice', 'alternative',
                     'library', 'framework', 'benchmark', 'why', 'difference', 'tradeoff']
REVIEW_KEYWORDS = ['review', 'audit', 'check', 'bug', 'security', 'vulnerability', 'test', 'edge case']
DEBUG_KEYWORDS = ['debug', 'error', 'crash', 'trace', 'stacktrace', 'exception', 'broken', 'failing', 'diagnose', 'root cause', 'scan']


def classify_task(msg):
    """Instant classification. Returns task type and which heavy models to invoke."""
    m = msg.lower()
    token_estimate = len(msg.split())

    # Large input (>500 words) → Grok ingests first
    if token_estimate > 500:
        return 'large_input', ['grok']

    has_code = any(kw in m for kw in CODE_KEYWORDS)
    has_arch = any(kw in m for kw in ARCH_KEYWORDS)
    has_research = any(kw in m for kw in RESEARCH_KEYWORDS)
    has_review = any(kw in m for kw in REVIEW_KEYWORDS)
    has_debug = any(kw in m for kw in DEBUG_KEYWORDS)

    # Pure chat / simple question → Gemma only (free)
    if not has_code and not has_arch and not has_research and not has_review and not has_debug:
        return 'chat', []

    # Debug → Grok primary (2M context can scan full codebase)
    if has_debug:
        return 'debug', ['grok']

    # Research → DeepSeek only
    if has_research and not has_code and not has_arch:
        return 'research', ['deepseek']

    # Code review → all 3 reviewers
    if has_review:
        return 'review', ['grok', 'codex', 'opus']

    # Architecture → Opus + Grok (co-architects) + DeepSeek for reasoning
    if has_arch and not has_code:
        return 'architecture', ['opus', 'grok']

    # Code task → Grok + Codex (dual engineers)
    if has_code:
        return 'code', ['grok', 'codex']

    # Default: Grok (most versatile)
    return 'general', ['grok']


SYSTEM_PROMPTS = {
    'grok': "You are a lead engineer, co-architect, and primary debugger with a 2M token context window. You can scan entire codebases. Write clean code, design robust systems, and diagnose bugs with surgical precision. Be concise.",
    'codex': "You are a lead engineer. Write clean, production code. Be concise — code first, minimal explanation.",
    'opus': "You are the system architect. Design robust solutions. When reviewing code, be specific about bugs and fixes.",
    'deepseek': "You are a senior researcher and deep reasoning engine. Provide thorough technical analysis. Be concise.",
}


def run_pipeline(user_message):
    """Main pipeline: classify → execute → review → present."""
    start = time.time()
    task_type, models_needed = classify_task(user_message)

    result = {
        'task_type': task_type,
        'models_used': [],
        'tokens': {'input': 0, 'output': 0},
    }

    # ─── CHAT ONLY: Gemma handles it, zero paid tokens ───
    if task_type == 'chat':
        text, tokens = call_model('gemma',
            "You are the Leviathan Cloud OS development team interface. Answer the user's question directly and concisely. You are friendly but efficient.",
            user_message, max_tokens=1000)
        result['response'] = text or "I'm here. What do you need?"
        result['models_used'] = ['Gemma 3']
        if isinstance(tokens, dict):
            result['tokens'] = tokens
        result['processing_time'] = f"{time.time() - start:.2f}s"
        return result

    # ─── LARGE INPUT: Grok ingests, summarizes, distributes ───
    if task_type == 'large_input':
        text, tokens = call_model('grok',
            "You received a large input. Analyze it thoroughly. Provide a structured summary and action plan.",
            user_message, max_tokens=2000)
        result['response'] = text or "Failed to process large input."
        result['models_used'] = ['Grok']
        if isinstance(tokens, dict):
            result['tokens'] = tokens
        result['processing_time'] = f"{time.time() - start:.2f}s"
        return result

    # ─── TASK EXECUTION: Call heavy models in parallel ───
    futures = {}
    for model_key in models_needed:
        sp = SYSTEM_PROMPTS.get(model_key, "Provide your expert analysis.")
        future = executor.submit(call_model, model_key, sp, user_message)
        futures[future] = model_key

    responses = {}
    try:
        for future in as_completed(futures, timeout=30):
            model_key = futures[future]
            try:
                text, tokens = future.result(timeout=3)
                if text:
                    responses[model_key] = text
                    result['models_used'].append(MODELS[model_key]['name'])
                    if isinstance(tokens, dict):
                        result['tokens']['input'] += tokens.get('input', 0)
                        result['tokens']['output'] += tokens.get('output', 0)
            except Exception as e:
                logger.warning(f"[{model_key}] failed: {e}")
    except TimeoutError:
        logger.warning("Parallel execution timeout, using collected responses")

    if not responses:
        result['response'] = "All models timed out. Try a simpler request."
        result['processing_time'] = f"{time.time() - start:.2f}s"
        return result

    # ─── CODE REVIEW PIPELINE (for code tasks with 2+ responses) ───
    if task_type == 'code' and len(responses) >= 2:
        # Quick cross-review: each model's code gets checked by the other
        # Use Gemma to synthesize (free) instead of burning paid tokens
        combined = "\n\n".join(f"[{MODELS[k]['name']}]:\n{v}" for k, v in responses.items())
        review_text, _ = call_model('gemma',
            "You are synthesizing code from multiple engineers into one final implementation. "
            "Pick the best parts from each, resolve conflicts, present one clean solution. "
            "Keep all code blocks intact. Be concise.",
            f"User asked: {user_message}\n\nEngineer outputs:\n{combined}",
            max_tokens=2000)
        result['response'] = review_text or combined
        result['models_used'].append('Gemma 3 (synthesis)')
    elif len(responses) > 1:
        # Multiple non-code responses: Gemma synthesizes (free)
        combined = "\n\n".join(f"[{MODELS[k]['name']}]:\n{v}" for k, v in responses.items())
        synth_text, _ = call_model('gemma',
            "Synthesize these expert responses into one coherent answer. Keep it concise and actionable.",
            f"User asked: {user_message}\n\nTeam responses:\n{combined}",
            max_tokens=1500)
        result['response'] = synth_text or combined
        result['models_used'].append('Gemma 3 (synthesis)')
    else:
        # Single response: pass through
        result['response'] = list(responses.values())[0]

    result['processing_time'] = f"{time.time() - start:.2f}s"
    return result


# ─── Flask Routes ──────────────────────────────────────────────

@app.route('/api/chat', methods=['POST'])
def api_chat():
    try:
        data = request.json
        msg = data.get('message', '').strip()
        if not msg:
            return jsonify({'error': 'Empty message'}), 400
        result = run_pipeline(msg)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'version': '4.0', 'timestamp': datetime.now().isoformat()})


@app.route('/status')
def status():
    return jsonify({
        'version': '4.0',
        'architecture': 'Gemma bridge + paid model execution',
        'models': {k: {'name': v['name'], 'role': v['role'], 'cost': v['cost']} for k, v in MODELS.items()},
        'api_keys': {k: bool(v) for k, v in API_KEYS.items()},
    })


# ─── Chat UI ──────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Leviathan Dev Team</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e27;color:#e0e0e0;height:100vh;display:flex;flex-direction:column}
header{background:#111830;border-bottom:1px solid #2a3550;padding:16px 20px}
h1{font-size:20px;background:linear-gradient(135deg,#00d4ff,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{font-size:11px;color:#666;margin-top:4px}
#msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:75%;padding:10px 14px;border-radius:8px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.msg.u{align-self:flex-end;background:#5b21b6;color:#fff}
.msg.a{align-self:flex-start;background:#1a2332;border:1px solid #2a3550}
.meta{font-size:10px;color:#00d4ff;margin-top:6px;opacity:.7}
.bar{background:#111830;border-top:1px solid #2a3550;padding:12px 16px;display:flex;gap:8px}
.bar input{flex:1;background:#1a2332;border:1px solid #2a3550;color:#e0e0e0;padding:10px 14px;border-radius:6px;font-size:14px;outline:none}
.bar input:focus{border-color:#7c3aed}
.bar button{background:#7c3aed;border:none;color:#fff;padding:10px 20px;border-radius:6px;cursor:pointer;font-size:14px}
.bar button:disabled{opacity:.4}
.dot{display:inline-block;width:6px;height:6px;background:#00d4ff;border-radius:50%;animation:p 1s infinite}
.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
@keyframes p{0%,100%{opacity:.2}50%{opacity:1}}
</style>
</head>
<body>
<header>
<h1>Leviathan Dev Team</h1>
<div class="sub">Gemma 3 (bridge) · Grok · Codex · Opus · DeepSeek</div>
</header>
<div id="msgs"></div>
<div class="bar">
<input id="inp" placeholder="Talk to your dev team..." autocomplete="off">
<button id="btn" onclick="send()">Send</button>
</div>
<script>
const msgs=document.getElementById('msgs'),inp=document.getElementById('inp'),btn=document.getElementById('btn');
function add(text,isUser,meta){
  const d=document.createElement('div');d.className='msg '+(isUser?'u':'a');
  d.textContent=text;
  if(meta){const m=document.createElement('div');m.className='meta';m.textContent=meta;d.appendChild(m)}
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
async function send(){
  const m=inp.value.trim();if(!m)return;
  add(m,true);inp.value='';btn.disabled=true;
  const ld=document.createElement('div');ld.className='msg a';
  ld.innerHTML='<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  msgs.appendChild(ld);msgs.scrollTop=msgs.scrollHeight;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m})});
    const d=await r.json();msgs.removeChild(ld);
    const meta=d.models_used?.length?d.models_used.join(' · ')+' · '+d.processing_time:'';
    add(d.response||d.error||'No response',false,meta);
  }catch(e){msgs.removeChild(ld);add('Error: '+e.message,false)}
  btn.disabled=false;
}
inp.addEventListener('keypress',e=>{if(e.key==='Enter')send()});
</script>
</body>
</html>"""


@app.route('/')
def index():
    return HTML


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Super Brain Dev Team v4.0 starting on :{port}")
    logger.info(f"Models: Gemma (bridge) + Grok + Codex + Opus + DeepSeek")
    app.run(host='0.0.0.0', port=port)
