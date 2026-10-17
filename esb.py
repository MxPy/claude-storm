#!/usr/bin/env python3
"""esb - event storming board. One .md file -> local interactive board. Stdlib only.
Usage: esb.py init|serve|check|next|snap|diff [file.md] [--port N] [--mode brownfield] [--force]"""
import sys, re, os, json, shutil, argparse, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

TYPES = {'event', 'cmd', 'actor', 'policy', 'read', 'ext', 'agg', 'hot', 'q', 'note'}
P1 = {'event', 'hot', 'q', 'note'}
P2 = P1 | {'actor', 'cmd', 'policy', 'read', 'ext'}
ALLOWED = {1: P1, 2: P2, 3: TYPES}
PFX = dict(event='E', cmd='C', actor='A', policy='P', read='R', ext='X', agg='G', hot='H', q='Q', note='N')
EL = re.compile(r'^- (\w+) (\w+): (.*?)(?: \| ((?:\w+=\S+ ?)+))?\s*$')
LOCK = threading.Lock()


def parse(path):
    lines = open(path, encoding='utf-8').read().split('\n')
    b = dict(title='', phase=1, mode='greenfield', items=[], lines=lines)
    ctx, last = '', None
    for n, l in enumerate(lines):
        h = re.match(r'^(phase|mode):\s*(\S+)', l)
        if h:
            b[h[1]] = int(h[2][0]) if h[1] == 'phase' else h[2]
        elif l.startswith('# '):
            b['title'] = l[2:]
        elif l.startswith('## '):
            ctx, last = l[3:].strip(), None
        elif EL.match(l):
            m = EL.match(l)
            kv = dict(p.split('=', 1) for p in (m[4] or '').split())
            last = dict(id=m[1], type=m[2], text=m[3], kv=kv, ctx=ctx, line=n, comments=[])
            b['items'].append(last)
        elif last and re.match(r'^\s+> ', l):
            last['comments'].append(l.strip()[2:])
    return b


def fmt(it):
    kv = ' '.join(f'{k}={v}' for k, v in it['kv'].items())
    return f"- {it['id']} {it['type']}: {it['text']}" + (f' | {kv}' if kv else '')


def status(it):
    return it['kv'].get('st') or ('hyp' if it['kv'].get('src') == 'agent' else 'ok')


def by(it):
    return [x for x in it['kv'].get('by', '').split(',') if x]


def check(b):
    out, ids, p, used, hyp = [], {}, b['phase'], set(), 0
    for it in b['items']:
        if it['id'] in ids:
            out.append(['E', f"{it['id']}: duplicate ID"])
        ids[it['id']] = it
    live = [i for i in b['items'] if status(i) != 'rej']
    for it in live:
        i, t, kv = it['id'], it['type'], it['kv']
        if t not in TYPES:
            out.append(['E', f'{i}: unknown type {t}'])
        elif t not in ALLOWED.get(p, TYPES):
            out.append(['E', f'{i}: type {t} not allowed in phase {p}'])
        for r in by(it) + ([kv['agg']] if kv.get('agg') else []):
            used.add(r)
            if r not in ids:
                out.append(['E', f'{i}: unknown reference {r}'])
        if p >= 2 and t == 'event' and not by(it):
            out.append(['E', f'{i}: event without a cause (by=)'])
        if p >= 2 and t == 'cmd' and not by(it):
            out.append(['E', f'{i}: command without an actor/policy (by=)'])
        if p >= 3 and t == 'event' and 'agg' not in kv:
            out.append(['W', f'{i}: event without an aggregate (agg=)'])
        if kv.get('code') and not os.path.exists(kv['code'].split(':')[0]):
            out.append(['W', f"{i}: file not found {kv['code'].split(':')[0]}"])
        if status(it) == 'disp':
            out.append(['W', f'{i}: DISPUTED - needs a decision'])
        hyp += status(it) == 'hyp'
    if p >= 2:
        for it in live:
            if it['type'] in ('actor', 'policy', 'read', 'ext') and not by(it) and it['id'] not in used:
                out.append(['W', f"{it['id']}: orphaned element"])
    if hyp:
        out.append(['W', f'{hyp} hypotheses awaiting confirmation'])
    return out


def view(b):
    items = [dict(id=i['id'], type=i['type'], text=i['text'], ctx=i['ctx'], comments=i['comments'], by=by(i),
                  st=status(i), src=i['kv'].get('src', 'biz')) for i in b['items']]
    return dict(title=b['title'], phase=b['phase'], mode=b['mode'], issues=check(b), items=items)


def write(path, lines):
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    os.replace(path + '.tmp', path)


def edit(path, r):
    with LOCK:
        b = parse(path)
        L, op = b['lines'], r['op']
        it = next((i for i in b['items'] if i['id'] == r.get('id')), None)
        if op == 'add':
            t = r['type']
            nums = [int(re.sub(r'\D', '', i['id']) or 0) for i in b['items'] if i['id'].startswith(PFX.get(t, 'N'))]
            kv = dict(src='biz', st='ok')
            if r.get('by'):
                kv['by'] = r['by'].replace(' ', '')
            new = dict(id=f"{PFX.get(t, 'N')}{max(nums + [0]) + 1}", type=t, text=r['text'], kv=kv)
            L.insert(it['line'] + 1 + len(it['comments']) if it else len(L), fmt(new))
        elif it and op == 'set':
            it['text'] = r.get('text', it['text'])
            if 'st' in r:
                it['kv']['st'] = r['st']
            L[it['line']] = fmt(it)
        elif it and op == 'comment':
            L.insert(it['line'] + 1 + len(it['comments']), '  > [biz] ' + r['text'])
        elif it and op == 'del':
            del L[it['line']:it['line'] + 1 + len(it['comments'])]
        write(path, L)


def snap_path(path):
    return os.path.join('.esb', os.path.basename(path) + '.snap')


def diff(path):
    sp = snap_path(path)
    if not os.path.exists(sp):
        return 'no snapshot (run esb.py snap) - read the whole file'
    new, old = parse(path), parse(sp)
    a, c, out = {i['id']: i for i in old['items']}, {i['id']: i for i in new['items']}, []
    sig = lambda i: (i['type'], i['text'], tuple(sorted(i['kv'].items())), i['ctx'], tuple(i['comments']))
    if old['phase'] != new['phase']:
        out.append(f"phase {old['phase']} -> {new['phase']}")
    for i, it in c.items():
        if i not in a:
            out.append('+ ' + fmt(it) + f"  [{it['ctx']}]")
        elif sig(a[i]) != sig(it):
            out.append('~ ' + fmt(it))
            out += ['    > ' + x for x in it['comments'] if x not in a[i]['comments']]
    out += [f'- {i} (removed)' for i in a if i not in c]
    return '\n'.join(out) or 'no changes since the last snapshot'


def serve(path, port):
    class H(BaseHTTPRequestHandler):
        def log_message(s, *a): pass

        def send(s, body, ct='application/json'):
            d = body.encode()
            s.send_response(200)
            s.send_header('Content-Type', ct + '; charset=utf-8')
            s.send_header('Content-Length', str(len(d)))
            s.end_headers()
            s.wfile.write(d)

        def do_GET(s):
            s.send(json.dumps(view(parse(path))) if s.path.startswith('/api/board') else HTML,
                   'application/json' if s.path.startswith('/api/') else 'text/html')

        def do_POST(s):
            edit(path, json.loads(s.rfile.read(int(s.headers['Content-Length']))))
            s.send('{"ok":1}')

    print(f'Board: http://127.0.0.1:{port}  (file: {path})')
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()


TEMPLATE = """# Event Storming: {title}
mode: {mode}
phase: 1

## Main context
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['init', 'serve', 'check', 'next', 'snap', 'diff'])
    ap.add_argument('file', nargs='?', default='event_storming.md')
    ap.add_argument('--port', type=int, default=8787)
    ap.add_argument('--mode', default='greenfield')
    ap.add_argument('--title', default='New project')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    f = a.file
    if a.cmd == 'init':
        if os.path.exists(f):
            sys.exit(f'{f} already exists')
        open(f, 'w', encoding='utf-8').write(TEMPLATE.format(title=a.title, mode=a.mode))
        print('created', f)
    elif a.cmd == 'serve':
        serve(f, a.port)
    elif a.cmd == 'snap':
        os.makedirs('.esb', exist_ok=True)
        shutil.copy(f, snap_path(f))
        print('snapshot saved')
    elif a.cmd == 'diff':
        print(diff(f))
    else:
        b = parse(f)
        iss = check(b)
        for lv, m in iss:
            print(lv, m)
        errs = [m for lv, m in iss if lv == 'E']
        if a.cmd == 'check':
            print(f"phase {b['phase']}: {len(b['items'])} items, {len(errs)} errors")
            sys.exit(1 if errs else 0)
        blockers = [m for lv, m in iss if lv == 'E' or 'DISPUTED' in m or 'hypotheses' in m]
        if blockers and not a.force:
            sys.exit('Not advancing - resolve the above (or use --force)')
        if b['phase'] >= 3:
            sys.exit('Last phase - generate the implementation plan')
        L = b['lines']
        for n, l in enumerate(L):
            if re.match(r'^phase:', l):
                L[n] = f"phase: {b['phase'] + 1}"
        write(f, L)
        print('phase ->', b['phase'] + 1)


HTML = r'''<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Event Storming</title>
<style>
*{box-sizing:border-box}
body{margin:0;font:13px/1.4 system-ui,sans-serif;display:flex;height:100vh;color:#222;background:#f6f5f1}
#cv{flex:1;overflow:auto;position:relative}
#side{width:300px;border-left:1px solid #d8d5cc;padding:12px;overflow:auto;background:#fff}
.n{position:absolute;width:112px;min-height:56px;padding:6px;border-radius:2px;box-shadow:1px 2px 3px #0003;cursor:pointer;overflow:hidden;font-size:12px;color:#222}
.n small{display:block;opacity:.6;font-size:10px}
.hyp{opacity:.7;outline:2px dashed #555}.disp{outline:3px solid #d00}.rej{opacity:.25;text-decoration:line-through}.sel{outline:3px solid #000}
.lane{position:absolute;left:6px;font-weight:600;color:#888}
.E{color:#c00}.W{color:#a60}
button,input,select{font:inherit;margin:2px 0}input{width:100%;padding:3px}
@media(prefers-color-scheme:dark){body{background:#1b1b1b;color:#eee}#side{background:#252525;border-color:#444}input,select{background:#333;color:#eee;border:1px solid #555}}
</style>
<div id=cv></div><div id=side></div>
<script>
const C={event:'#f5a623',cmd:'#6aa9ff',actor:'#ffe66d',policy:'#c9a0ff',read:'#7bd88f',ext:'#ff9ecb',agg:'#fff3a3',hot:'#ff6b6b',q:'#ff9a9a',note:'#ddd'};
const R={actor:0,cmd:1,policy:1,event:2,read:3,ext:3,agg:4,hot:5,q:5,note:5};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let B=null,sel=null,last='';
const api=o=>fetch('/api/edit',{method:'POST',body:JSON.stringify(o)}).then(()=>load(1));
async function load(f){
  const t=await(await fetch('/api/board')).text();
  if(t==last||(!f&&document.activeElement.tagName=='INPUT'))return;
  last=t;B=JSON.parse(t);draw();
}
function draw(){
  const it=B.items,m={};it.forEach(i=>m[i.id]=i);let k=0;
  it.forEach(i=>i.col=i.type=='event'?k++:null);
  for(let p=0;p<4;p++)it.forEach(i=>{
    if(i.col!=null)return;
    const rev=it.find(e=>e.col!=null&&e.by.includes(i.id)),fw=i.by.map(x=>m[x]).find(x=>x&&x.col!=null);
    const s=i.type=='policy'?(fw||rev):(rev||fw);if(s)i.col=s.col;
  });
  let pv=0;it.forEach(i=>{if(i.col==null)i.col=pv;else pv=i.col});
  const lanes=[...new Set(it.map(i=>i.ctx))],cnt={},cell={};
  it.forEach(i=>{const key=[i.ctx,R[i.type],i.col].join();i.sub=cell[key]=(cell[key]??-1)+1;cnt[i.col]=Math.max(cnt[i.col]||0,i.sub+1)});
  const xs=[];let x=60;
  for(let c=0;c<=Math.max(...it.map(i=>i.col),0);c++){xs[c]=x;x+=(cnt[c]||1)*124}
  const LH=6*70+30;
  it.forEach(i=>{i.x=xs[i.col]+i.sub*124;i.y=lanes.indexOf(i.ctx)*LH+30+(R[i.type]??5)*70});
  let h=lanes.map((l,j)=>`<div class=lane style="top:${j*LH+4}px">${esc(l)}</div>`).join('');
  const lines=it.flatMap(i=>i.by.map(r=>{
    const a=m[r];if(!a)return'';
    const dx=i.x-a.x,dy=i.y-a.y,t=Math.min(56/Math.abs(dx||1e-6),30/Math.abs(dy||1e-6),.5);
    return`<line x1=${a.x+56+dx*t} y1=${a.y+28+dy*t} x2=${i.x+56-dx*t} y2=${i.y+28-dy*t} stroke="#888" marker-end="url(#a)"/>`;
  })).join('');
  h+=`<svg style="position:absolute;left:0;top:0;pointer-events:none" width=${x+200} height=${lanes.length*LH+50}><defs><marker id=a markerWidth=8 markerHeight=8 refX=7 refY=4 orient=auto><path d="M0,0L8,4L0,8z" fill="#888"/></marker></defs>${lines}</svg>`;
  h+=it.map(i=>`<div class="n ${i.st} ${sel==i.id?'sel':''}" style="left:${i.x}px;top:${i.y}px;background:${C[i.type]||'#ddd'}" onclick="sel='${i.id}';draw()"><small>${i.id} ${i.type}${i.src=='agent'?' (agent)':''}${i.comments.length?' / '+i.comments.length+' comments':''}</small>${esc(i.text)}</div>`).join('');
  cv.innerHTML=h;
  const s=m[sel],id=s?s.id:'';
  side.innerHTML=`<b>${esc(B.title)}</b><br>Phase ${B.phase}, mode ${B.mode}<hr>`
   +(B.issues.map(([l,t])=>`<div class=${l}>${esc(t)}</div>`).join('')||'No issues')+'<hr>'
   +(s?`<b>${s.id} ${s.type}</b> (${s.st}, ${s.src})
    <input value="${esc(s.text)}" onchange="api({op:'set',id:'${id}',text:this.value})">
    <button onclick="api({op:'set',id:'${id}',st:'ok'})">Confirm</button>
    <button onclick="api({op:'set',id:'${id}',st:'disp'})">Disputed</button>
    <button onclick="api({op:'set',id:'${id}',st:'rej'})">Reject</button>
    <button onclick="if(confirm('Delete ${id}?'))api({op:'del',id:'${id}'})">Delete</button>
    ${s.comments.map(c=>`<div>&gt; ${esc(c)}</div>`).join('')}
    <input placeholder="Comment, then Enter" onkeydown="if(event.key=='Enter')api({op:'comment',id:'${id}',text:this.value})"><hr>`:'<i>Click a sticky note</i><hr>')
   +`Add ${s?'after '+id:'at the end'}:<select id=ty>${Object.keys(C).map(t=>`<option>${t}</option>`).join('')}</select>
    <input id=nt placeholder="Text"><input id=nb placeholder="by (np. C1,A1)">
    <button onclick="api({op:'add',id:'${id}',type:ty.value,text:nt.value,by:nb.value})">Add</button>`;
}
load(1);setInterval(()=>load(),1500);
</script>
'''

if __name__ == '__main__':
    main()
