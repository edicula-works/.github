"""Job semanal: põe no ciclo as issues pela semana nominal do título (N-W##-…/Gate W##-ENC;
times sem plano usam o prazo), avisa pendências externas vencidas e publica o relatório da
semana como comentário no gate de encerramento (Gate W##-ENC) de cada time.

Lê LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET (app "Edicula Agents", preferido) ou LINEAR_API_KEY.
Imprime só contagens (o log é público). SECO=1 imprime o que faria sem mutar nada.
"""
import json, os, re, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime

def post(url, corpo, auth):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={'Content-Type': 'application/json; charset=utf-8', 'Authorization': auth})
    return json.load(urllib.request.urlopen(req, timeout=60))

_auth = None

def linear_auth():
    global _auth
    if _auth is None:
        if os.environ.get('LINEAR_CLIENT_ID') and os.environ.get('LINEAR_CLIENT_SECRET'):
            corpo = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': os.environ['LINEAR_CLIENT_ID'],
                'client_secret': os.environ['LINEAR_CLIENT_SECRET'], 'scope': 'read,write'}).encode()
            req = urllib.request.Request('https://api.linear.app/oauth/token', data=corpo, headers={'Content-Type': 'application/x-www-form-urlencoded'})
            _auth = 'Bearer ' + json.load(urllib.request.urlopen(req, timeout=60))['access_token']
        else:
            _auth = os.environ['LINEAR_API_KEY']
    return _auth

def gql(q, v=None):
    d = post('https://api.linear.app/graphql', {'query': q, 'variables': v or {}}, linear_auth())
    if d.get('errors'): raise SystemExit('erro na API do Linear')
    return d['data']

dia = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00')).date()
quando = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
SECO = os.environ.get('SECO') == '1'
AGENT = re.compile(r'\*\*Agent (\w+)\*\* iniciado')
NOMES = {'preparar': 'preparações', 'revisar': 'revisões de PR', 'plano': 'revisões de plano'}
SEMANA = re.compile(r'(?:^|\s)N-W(\d+)-')
GATE_ENC = re.compile(r'Gate W(\d+)-ENC')

def dias(h):
    return f'{h / 24:.1f} d'.replace('.', ',') if h >= 24 else f'{h:.0f} h'

def relatorio(t, desde):
    entregues, cursor = [], None
    while True:
        r = gql('query($id:ID,$c:String,$d:DateTimeOrDuration){ issues(first:100, after:$c, filter:{team:{id:{eq:$id}}, completedAt:{gte:$d}, state:{type:{eq:"completed"}}}){ nodes { identifier title url startedAt completedAt assignee { name displayName } labels { nodes { name } } } pageInfo { hasNextPage endCursor } } }', {'id': t['id'], 'c': cursor, 'd': desde})['issues']
        entregues += r['nodes']
        if not r['pageInfo']['hasNextPage']:
            break
        cursor = r['pageInfo']['endCursor']
    proprias = [i for i in entregues if not any(l['name'] == 'Origem: Hub' for l in i['labels']['nodes'])]
    tempos = [(i, (quando(i['completedAt']) - quando(i['startedAt'])).total_seconds() / 3600) for i in proprias if i.get('startedAt')]
    agentes, duracoes = {}, []
    r = gql('query($id:ID,$d:DateTimeOrDuration){ issues(first:100, filter:{team:{id:{eq:$id}}, updatedAt:{gte:$d}}){ nodes { comments(first:50, filter:{createdAt:{gte:$d}}){ nodes { body createdAt } } } } }', {'id': t['id'], 'd': desde})['issues']['nodes']
    for i in r:
        cs = sorted(i['comments']['nodes'], key=lambda c: c['createdAt'])
        for n, c in enumerate(cs):
            m = AGENT.search(c['body'])
            if not m:
                continue
            agentes[m.group(1)] = agentes.get(m.group(1), 0) + 1
            fim = next((d for d in cs[n + 1:] if d['body'].startswith('🤖 **Agent** (')), None)
            if fim:
                duracoes.append((quando(fim['createdAt']) - quando(c['createdAt'])).total_seconds() / 60)
    if not entregues and not agentes:
        return None
    hub = len(entregues) - len(proprias)
    linhas = [f'📊 **Semana em {t["name"]}**: {len(entregues)} issue(s) entregue(s)' + (f' ({hub} vinda(s) do Hub)' if hub else '') + (f' · ciclo médio {dias(sum(h for _, h in tempos) / len(tempos))}' if tempos else '')]
    pessoas = {}
    for i, h in tempos:
        a = i['assignee'] or {}
        nome = a.get('name') or 'sem responsável'
        if '@' in nome:
            nome = a.get('displayName') or nome.split('@')[0]
        pessoas.setdefault(nome, []).append(h)
    if pessoas:
        linhas.append('• Por pessoa: ' + ', '.join(f'{p} {len(hs)} ({dias(sum(hs) / len(hs))})' for p, hs in sorted(pessoas.items(), key=lambda x: -len(x[1]))))
    if agentes:
        linhas.append('• Agents: ' + ', '.join(f'{q} {NOMES.get(k, k)}' for k, q in agentes.items()) + (f' · {sum(duracoes) / len(duracoes):.0f} min em média' if duracoes else ''))
    for i, h in sorted(tempos, key=lambda x: -x[1])[:10]:
        linhas.append(f'• {i["identifier"]} {i["title"][:70]} ({dias(h)})')
    return '\n'.join(linhas)

hoje = date.today()
postas, realocadas, vencidas, relatorios = 0, 0, 0, 0
for t in gql('{ teams { nodes { id name } } }')['teams']['nodes']:
    nos = gql('query($id:String!){ team(id:$id){ cycles(first:50){ nodes { id name startsAt endsAt } } } }', {'id': t['id']})['team']['cycles']['nodes']
    por_nome = {c['name']: c['id'] for c in nos}
    nome_de = {c['id']: c['name'] for c in nos}
    fechados = sorted((c for c in nos if dia(c['endsAt']) <= hoje), key=lambda c: dia(c['endsAt']))
    abertas, cursor = [], None
    while True:
        r = gql('query($id:ID,$c:String){ issues(first:100, after:$c, filter:{team:{id:{eq:$id}}, state:{type:{nin:["completed","canceled"]}}}){ nodes { id identifier title dueDate cycle { id name } labels { nodes { name } } } pageInfo { hasNextPage endCursor } } }', {'id': t['id'], 'c': cursor})['issues']
        abertas += r['nodes']
        if not r['pageInfo']['hasNextPage']:
            break
        cursor = r['pageInfo']['endCursor']
    venc = []
    for i in abertas:
        m = SEMANA.search(i['title']) or GATE_ENC.search(i['title'])
        alvo = None
        if m:
            alvo = por_nome.get(f'W{int(m.group(1)):02d}')
        elif i['dueDate'] and not i['cycle'] and nos:
            p = date.fromisoformat(i['dueDate'])
            alvo = next((c['id'] for c in sorted(nos, key=lambda c: dia(c['startsAt'])) if dia(c['startsAt']) <= p < dia(c['endsAt'])), None)
        if alvo and (not i['cycle'] or i['cycle']['id'] != alvo):
            if SECO:
                print(f'(seco) {i["identifier"]}: {(i["cycle"] or {}).get("name") or "sem ciclo"} → {nome_de.get(alvo, alvo)} · {i["title"][:50]}')
            else:
                gql('mutation($id:String!,$c:String!){ issueUpdate(id:$id, input:{cycleId:$c}){ success } }', {'id': i['id'], 'c': alvo})
            if i['cycle']:
                realocadas += 1
            else:
                postas += 1
        if i['dueDate'] and date.fromisoformat(i['dueDate']) < hoje and any(l['name'] == 'Pendência externa' for l in i['labels']['nodes']):
            venc.append(i)
    # relatório + pendências no gate da semana que fechou
    texto = relatorio(t, (datetime.now().astimezone() - __import__('datetime').timedelta(days=7)).isoformat())
    vencidas += len(venc)
    if venc:
        aviso = '\n'.join(['⚠️ **Pendência(s) externa(s) vencida(s)**'] + [f'• {i["identifier"]} {i["title"][:80]} (prazo {i["dueDate"]})' for i in venc[:20]])
        texto = (texto + '\n\n' + aviso) if texto else aviso
    if texto and fechados:
        semana = fechados[-1]['name']
        gate = gql('query($id:ID,$t:String!){ issues(first:1, filter:{team:{id:{eq:$id}}, title:{contains:$t}}){ nodes { id identifier } } }', {'id': t['id'], 't': f'Gate {semana}-ENC'})['issues']['nodes']
        if gate:
            corpo = f'{texto}\n\n_(job semanal, {hoje.isoformat()})_'
            if SECO:
                print(f'--- {t["name"]} → comentário em {gate[0]["identifier"]}\n{corpo}')
            else:
                gql('mutation($id:String!,$b:String!){ commentCreate(input:{issueId:$id, body:$b}){ success } }', {'id': gate[0]['id'], 'b': corpo})
            relatorios += 1
        else:
            print(f'sem gate {semana}-ENC em {t["name"]}: relatório não publicado')
print(f'issues postas em ciclo: {postas}; realocadas p/ semana nominal: {realocadas}; pendências vencidas: {vencidas}; relatórios: {relatorios}')
