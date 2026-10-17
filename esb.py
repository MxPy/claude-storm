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
        for r in by(it) + [kv[k] for k in ('agg', 'at') if kv.get(k)]:
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
                  st=status(i), src=i['kv'].get('src', 'biz'), at=i['kv'].get('at', '')) for i in b['items']]
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
        elif it and op == 'move':
            tg = next((i for i in b['items'] if i['id'] == r.get('to')), None)
            if tg and tg is not it:
                blk = L[it['line']:it['line'] + 1 + len(it['comments'])]
                ins = tg['line'] if r.get('side') == 'before' else tg['line'] + 1 + len(tg['comments'])
                if ins > it['line']:
                    ins -= len(blk)
                del L[it['line']:it['line'] + len(blk)]
                L[ins:ins] = blk
        elif it and op == 'at':
            if r.get('to'):
                it['kv']['at'] = r['to']
            else:
                it['kv'].pop('at', None)
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
    ev = lambda bb: [i['id'] for i in bb['items'] if i['type'] == 'event']
    both = set(a) & set(c)
    if [x for x in ev(old) if x in both] != [x for x in ev(new) if x in both]:
        out.append('timeline: ' + ' > '.join(ev(new)))
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
:root{--bg:#eceff4;--dot:#c8cfdb;--lane:#ffffff70;--panel:#fff;--line:#e2e6ed;--ink:#1b2130;--mute:#6a7387;--acc:#4a56e2;--accbg:#e8eaff;--bad:#d23b3b;--warn:#a9690f}
@media(prefers-color-scheme:dark){:root{--bg:#12151b;--dot:#2b313d;--lane:#ffffff08;--panel:#1a1e26;--line:#2b313d;--ink:#e8ebf2;--mute:#8e98ac;--acc:#8d97ff;--accbg:#262b4f;--bad:#ff7d7d;--warn:#f0bd62}}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{display:grid;grid-template-columns:1fr 340px;grid-template-rows:auto 1fr;font:13px/1.45 "Segoe UI Variable Text","SF Pro Text",system-ui,sans-serif;color:var(--ink);background:var(--bg)}
#hd{grid-column:1/3;display:flex;align-items:center;gap:10px;padding:10px 18px;background:var(--panel);border-bottom:1px solid var(--line)}
#hd h1{font-size:15px;margin:0 8px 0 0;font-weight:650}
.pill{padding:2px 9px;border-radius:99px;background:var(--bg);color:var(--mute);font-size:12px}
.steps{display:flex;gap:4px;margin-left:auto}
.st{padding:4px 12px;border-radius:99px;color:var(--mute);border:1px solid var(--line)}
.st.done{color:var(--ink)}.st.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
#cv{position:relative;overflow:auto;background:radial-gradient(var(--dot) 1px,transparent 1.2px) 0 0/22px 22px local}
#side{overflow:auto;background:var(--panel);border-left:1px solid var(--line)}
.sec{padding:14px 16px;border-bottom:1px solid var(--line)}
.sec h4{margin:0 0 6px;font-size:12px;font-weight:600;color:var(--mute)}
.lane{position:absolute;left:0;border-top:1px solid var(--line);background:var(--lane)}
.lt{position:absolute;left:14px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:2px 10px;border-radius:99px;background:var(--panel);border:1px solid var(--line);font-weight:600;font-size:12px}
.cb{position:absolute;top:0;border-left:1px dashed var(--line)}
.cn{position:absolute;top:8px;font-size:11px;color:var(--mute);padding-left:6px}
.n{position:absolute;width:112px;min-height:60px;padding:17px 8px 7px;border-radius:7px;font-size:12px;line-height:1.3;color:#1d2230;border:1.5px solid #0002;box-shadow:0 1px 1px #0002,0 8px 14px -8px #0006;cursor:grab;user-select:none;touch-action:none}
.n i{position:absolute;left:8px;top:4px;font-style:normal;font-size:10px;opacity:.65}
.n u{position:absolute;right:5px;top:3px;text-decoration:none;font-size:9px;font-weight:700;padding:0 5px;border-radius:8px;background:#0002}
.n.hyp{border-style:dashed;border-color:#0008}
.n.disp{box-shadow:0 0 0 3px var(--bad),0 8px 14px -8px #0006}
.n.rej{opacity:.3;text-decoration:line-through}
.n.sel{box-shadow:0 0 0 3px var(--acc),0 8px 14px -8px #0006}
.n.drag{cursor:grabbing;z-index:9;box-shadow:0 0 0 3px var(--acc),0 18px 28px -10px #0009}
#band{position:absolute;top:0;background:var(--accbg);opacity:.7;pointer-events:none;display:none}
#ins{position:absolute;width:4px;margin-left:-2px;border-radius:2px;background:var(--acc);pointer-events:none;display:none;z-index:8}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;font-weight:600;font-size:12px;color:#1d2230}
textarea,input,select{width:100%;font:inherit;color:inherit;background:var(--bg);border:1px solid var(--line);border-radius:7px;padding:7px 9px;margin-top:6px}
textarea{resize:vertical;min-height:54px}
:focus-visible{outline:2px solid var(--acc);outline-offset:1px}
.seg{display:grid;grid-template-columns:repeat(4,1fr);margin-top:8px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{border:0;border-right:1px solid var(--line);background:none;color:var(--mute);padding:6px 0;font:inherit;cursor:pointer}
.seg button:last-child{border-right:0}.seg button.on{background:var(--accbg);color:var(--acc);font-weight:650}
.btn{border:1px solid var(--line);background:none;color:var(--ink);border-radius:7px;padding:6px 12px;font:inherit;cursor:pointer;margin:8px 6px 0 0}
.btn.p{background:var(--acc);border-color:var(--acc);color:#fff}.btn.d{color:var(--bad)}
.is{display:flex;gap:8px;padding:3px 0;cursor:pointer}
.is:before{content:"";width:8px;height:8px;margin-top:5px;border-radius:50%;flex:none;background:var(--warn)}.is.E:before{background:var(--bad)}
.cm{background:var(--bg);border-radius:9px;padding:6px 10px;margin-top:6px}
.lg{display:flex;flex-wrap:wrap;gap:6px}
details summary{cursor:pointer;color:var(--mute)}
</style>
<header id=hd></header><main id=cv></main><aside id=side></aside>
<script>
const T={event:['Event','#ffb347'],cmd:['Command','#7db7ff'],actor:['Actor','#ffe27a'],policy:['Policy','#c7a6ff'],read:['Read model','#8be0a4'],ext:['External system','#ff9fc6'],agg:['Aggregate','#fff0a0'],hot:['Hotspot','#ff7a7a'],q:['Question','#ffb8b8'],note:['Note','#e4e6eb']};
const R={actor:0,cmd:1,policy:1,event:2,read:3,ext:3,agg:4,hot:5,q:5,note:5};
const SN=['Big Picture','Process','Design'],ST=[['hyp','Hypothesis'],['ok','Confirmed'],['disp','Disputed'],['rej','Rejected']];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let B=null,sel=null,last='',G={},drag=null,addOpen=false;
const api=o=>fetch('/api/edit',{method:'POST',body:JSON.stringify(o)}).then(()=>load(1));
const pick=id=>{sel=id;draw()};
async function load(f){
  const t=await(await fetch('/api/board')).text();
  if(t==last||(!f&&/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)))return;
  last=t;B=JSON.parse(t);draw();
}
function draw(){
  const it=B.items,m={};it.forEach(i=>m[i.id]=i);let k=0;
  it.forEach(i=>i.col=i.type=='event'?k++:null);
  it.forEach(i=>{const a=m[i.at];if(i.type!='event'&&a&&a.type=='event')i.col=a.col});
  for(let p=0;p<4;p++)it.forEach(i=>{
    if(i.col!=null)return;
    const rev=it.find(e=>e.col!=null&&e.by.includes(i.id)),fw=i.by.map(x=>m[x]).find(x=>x&&x.col!=null);
    const s=i.type=='policy'?(fw||rev):(rev||fw);if(s)i.col=s.col;
  });
  let pv=0;it.forEach(i=>{if(i.col==null)i.col=pv;else pv=i.col});
  const lanes=[...new Set(it.map(i=>i.ctx))],cnt={},cell={};
  it.forEach(i=>{const key=[i.ctx,R[i.type],i.col].join();i.sub=cell[key]=(cell[key]??-1)+1;cnt[i.col]=Math.max(cnt[i.col]||0,i.sub+1)});
  const xs=[];let x=150;
  for(let c=0;c<=Math.max(...it.map(i=>i.col),0);c++){xs[c]=x;x+=(cnt[c]||1)*124}
  const LH=6*70+30,W=x+160,H=lanes.length*LH+40;
  G={m,xs,cnt,lanes,LH,H};
  it.forEach(i=>{i.x=xs[i.col]+i.sub*124;i.y=lanes.indexOf(i.ctx)*LH+34+(R[i.type]??5)*70});
  const sl=cv.scrollLeft,sp=cv.scrollTop;
  let h=lanes.map((l,j)=>`<div class=lane style="top:${j*LH}px;height:${LH}px;width:${W}px"></div><div class=lt style="top:${j*LH+6}px">${esc(l||'Board')}</div>`).join('');
  h+=xs.map((x,c)=>`<div class=cb style="left:${x-6}px;height:${H}px"></div><div class=cn style="left:${x-6}px">${c+1}</div>`).join('');
  const lines=it.flatMap(i=>i.by.map(r=>{
    const a=m[r];if(!a)return'';
    const dx=i.x-a.x,dy=i.y-a.y,t=Math.min(56/Math.abs(dx||1e-6),30/Math.abs(dy||1e-6),.5);
    return`<line x1=${a.x+56+dx*t} y1=${a.y+30+dy*t} x2=${i.x+56-dx*t} y2=${i.y+30-dy*t} style="stroke:var(--mute);stroke-width:1.5" marker-end="url(#a)"/>`;
  })).join('');
  h+=`<svg style="position:absolute;left:0;top:0;pointer-events:none" width=${W} height=${H}><defs><marker id=a markerWidth=8 markerHeight=8 refX=7 refY=4 orient=auto><path d="M0,0L8,4L0,8z" style="fill:var(--mute)"/></marker></defs>${lines}</svg>`;
  h+=it.map(i=>{const t=T[i.type]||T.note;return`<div class="n ${i.st} ${sel==i.id?'sel':''}" style="left:${i.x}px;top:${i.y}px;background:${t[1]}" onpointerdown="down(event,'${i.id}')" onpointermove="mv(event)" onpointerup="up(event)"><i>${t[0]}</i>${i.src=='agent'?'<u>AI</u>':''}${esc(i.text)}${i.comments.length?` <span style="opacity:.6">· ${i.comments.length}</span>`:''}</div>`}).join('');
  cv.innerHTML=h+'<div id=band></div><div id=ins></div>';
  cv.scrollLeft=sl;cv.scrollTop=sp;
  const ne=B.issues.filter(x=>x[0]=='E').length,nw=B.issues.length-ne;
  hd.innerHTML=`<h1>${esc(B.title.replace(/^Event Storming:\s*/,''))}</h1><span class=pill>${esc(B.mode)}</span><span class=pill>${it.length} stickies</span><span class=pill style="${ne?'color:var(--bad)':''}">${ne} errors · ${nw} warnings</span><div class=steps>${SN.map((n,j)=>`<span class="st ${B.phase==j+1?'on':B.phase>j+1?'done':''}">${j+1}. ${n}</span>`).join('')}</div>`;
  const s=m[sel],id=s?s.id:'',t=s?(T[s.type]||T.note):0;
  side.innerHTML=`<div class=sec><h4>Issues</h4>${B.issues.map(([l,x])=>`<div class="is ${l}" onclick="pick('${(x.match(/^(\w+):/)||[])[1]||''}')">${esc(x)}</div>`).join('')||'<span style="color:var(--mute)">Nothing to fix.</span>'}</div>`
  +(s?`<div class=sec><span class=chip style="background:${t[1]}">${t[0]}</span> <b>${id}</b> <span class=pill>${s.src=='agent'?'agent':'you'}</span>
    <textarea onchange="api({op:'set',id:'${id}',text:this.value})">${esc(s.text)}</textarea>
    <div class=seg>${ST.map(([k,n])=>`<button class="${s.st==k?'on':''}" onclick="api({op:'set',id:'${id}',st:'${k}'})">${n}</button>`).join('')}</div>
    ${s.at?`<button class=btn onclick="api({op:'at',id:'${id}',to:''})">Reset column</button>`:''}<button class="btn d" onclick="if(confirm('Delete ${id}?'))api({op:'del',id:'${id}'})">Delete</button></div>
    <div class=sec><h4>Discussion</h4>${s.comments.map(c=>`<div class=cm>${esc(c)}</div>`).join('')}<input placeholder="Write a comment, press Enter" onkeydown="if(event.key=='Enter'&&this.value)api({op:'comment',id:'${id}',text:this.value})"></div>`
   :`<div class=sec style="color:var(--mute)">Click a sticky to inspect it. Drag an event sideways to reorder the timeline. Drag any other sticky to another column to move it there.</div>`)
  +`<div class=sec><details ${addOpen?'open':''} ontoggle="addOpen=this.open"><summary>Add a sticky ${s?'after '+id:'at the end'}</summary>
    <select id=ty>${Object.entries(T).map(([k,v])=>`<option value=${k}>${v[0]}</option>`).join('')}</select>
    <input id=nt placeholder="Text"><input id=nb placeholder="Caused by (e.g. C1,A1)">
    <button class="btn p" onclick="if(nt.value)api({op:'add',id:'${id}',type:ty.value,text:nt.value,by:nb.value})">Add</button></details></div>
   <div class=sec><h4>Legend</h4><div class=lg>${Object.values(T).map(v=>`<span class=chip style="background:${v[1]}">${v[0]}</span>`).join('')}</div></div>`;
}
function target(d,e){
  const it=G.m[d.id],px=e.clientX-cv.getBoundingClientRect().left+cv.scrollLeft;
  let c=0,bd=1e9;G.xs.forEach((x,j)=>{const dd=Math.abs(px-(x+(G.cnt[j]||1)*62));if(dd<bd){bd=dd;c=j}});
  if(it.type!='event'){const e2=B.items.find(i=>i.type=='event'&&i.col==c);return{c,to:e2&&e2.id}}
  const ev=B.items.filter(i=>i.type=='event'&&i.ctx==it.ctx&&i!=it);
  if(!ev.length)return{c};
  const T2=ev.reduce((a,b)=>Math.abs(b.col-c)<Math.abs(a.col-c)?b:a);
  return{c:T2.col,to:T2.id,side:px<G.xs[T2.col]+(G.cnt[T2.col]||1)*62?'before':'after'};
}
function down(e,id){if(e.button)return;const n=e.currentTarget;drag={id,n,sx:e.clientX,x0:parseFloat(n.style.left),mv:0};n.setPointerCapture(e.pointerId)}
function mv(e){
  if(!drag)return;const dx=e.clientX-drag.sx;if(Math.abs(dx)>5)drag.mv=1;if(!drag.mv)return;
  drag.n.classList.add('drag');drag.n.style.left=drag.x0+dx+'px';
  const t=target(drag,e),b=document.getElementById('band'),n=document.getElementById('ins');
  b.style.display=n.style.display='none';if(!t.to)return;
  const it=G.m[drag.id],w=(G.cnt[t.c]||1)*124;
  if(it.type=='event')n.style.cssText=`display:block;left:${t.side=='before'?G.xs[t.c]-8:G.xs[t.c]+w-4}px;top:${G.lanes.indexOf(it.ctx)*G.LH}px;height:${G.LH}px`;
  else b.style.cssText=`display:block;left:${G.xs[t.c]-6}px;width:${w}px;height:${G.H}px`;
}
function up(e){
  const d=drag;if(!d)return;drag=null;
  if(!d.mv){pick(d.id);return}
  const t=target(d,e),it=G.m[d.id];
  if(!t.to||t.to==d.id||(it.type!='event'&&t.c==it.col)){draw();return}
  api(it.type=='event'?{op:'move',id:d.id,to:t.to,side:t.side}:{op:'at',id:d.id,to:t.to});
}
addEventListener('keydown',e=>{if(e.key=='Escape'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){sel=null;draw()}});
load(1);setInterval(()=>load(),1500);
</script>
'''

if __name__ == '__main__':
    main()