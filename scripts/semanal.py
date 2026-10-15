"""Job semanal: põe no ciclo as issues com prazo ainda sem ciclo, avisa pendências externas vencidas
e publica no #proj- de cada time o relatório de tempo da semana (issues entregues e agents).

Lê LINEAR_CLIENT_ID/LINEAR_CLIENT_SECRET (app "Edicula Agents", preferido) ou LINEAR_API_KEY, e SLACK_BOT_TOKEN. Imprime só contagens (o log é público).
"""
import json, os, re, unicodedata, urllib.parse, urllib.request
from datetime import date, datetime

def post(url, corpo, auth):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={'Content-Type': 'application/json; charset=utf-8', 'Authorization': auth})
    return json.load(urllib.request.urlopen(req, timeout=60))

_auth = None

def linear_auth():
    # App do Linear por client credentials (token novo a cada execução); senão, a chave pessoal.
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

def slack(metodo, **kw):
    return post('https://slack.com/api/' + metodo, kw, 'Bearer ' + os.environ['SLACK_BOT_TOKEN'])

def slug(t):
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')

dia = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00')).date()
quando = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00'))
SECO = os.environ.get('SECO') == '1'  # teste: imprime em vez de postar
AGENT = re.compile(r'\*\*Agent (\w+)\*\* iniciado')
NOMES = {'preparar': 'preparações', 'revisar': 'revisões de PR', 'plano': 'revisões de plano'}

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
    # Issues vindas do Hub têm início/entrega da importação: contam no total, não no tempo.
    proprias = [i for i in entregues if not any(l['name'] == 'Origem: Hub' for l in i['labels']['nodes'])]
    tempos = [(i, (quando(i['completedAt']) - quando(i['startedAt'])).total_seconds() / 3600) for i in proprias if i.get('startedAt')]
    # Agents: comentários "Agent X iniciado" da semana e o tempo até a publicação seguinte do agent.
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
    linhas = [f':bar_chart: *Semana em {t["name"]}*: {len(entregues)} issue(s) entregue(s)' + (f' ({hub} vinda(s) do Hub)' if hub else '') + (f' · ciclo médio {dias(sum(h for _, h in tempos) / len(tempos))}' if tempos else '')]
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
        linhas.append(f'• <{i["url"]}|{i["identifier"]}> {i["title"][:70]} ({dias(h)})')
    return '\n'.join(linhas)
hoje = date.today()
postas, vencidas, relatorios = 0, 0, 0
canais = {c['name']: c['id'] for c in slack('conversations.list', types='public_channel', limit=200).get('channels', [])}
for t in gql('{ teams { nodes { id name } } }')['teams']['nodes']:
    cy = sorted((dia(c['startsAt']), dia(c['endsAt']), c['id']) for c in gql('query($id:String!){ team(id:$id){ cycles(first:50){ nodes { id startsAt endsAt } } } }', {'id': t['id']})['team']['cycles']['nodes'])
    abertas, cursor = [], None
    while True:
        r = gql('query($id:ID,$c:String){ issues(first:100, after:$c, filter:{team:{id:{eq:$id}}, state:{type:{nin:["completed","canceled"]}}, dueDate:{null:false}}){ nodes { id dueDate cycle { id } labels { nodes { name } } title url } pageInfo { hasNextPage endCursor } } }', {'id': t['id'], 'c': cursor})['issues']
        abertas += r['nodes']
        if not r['pageInfo']['hasNextPage']:
            break
        cursor = r['pageInfo']['endCursor']
    venc = []
    for i in abertas:
        p = date.fromisoformat(i['dueDate'])
        if not i['cycle'] and cy:
            alvo = cy[0] if p < cy[0][0] else next((c for c in cy if c[0] <= p < c[1]), None)
            if alvo and not SECO:
                gql('mutation($id:String!,$i:IssueUpdateInput!){ issueUpdate(id:$id,input:$i){ success } }', {'id': i['id'], 'i': {'cycleId': alvo[2]}})
                postas += 1
        if p < hoje and any(l['name'] == 'Pendência externa' for l in i['labels']['nodes']):
            venc.append(i)
    canal = canais.get('proj-' + slug(t['name']))
    if venc and canal and not SECO:
        linhas = [f':warning: *{len(venc)} pendência(s) externa(s) vencida(s) em {t["name"]}*'] + [f'• <{i["url"]}|{i["title"]}> (prazo {i["dueDate"]})' for i in venc[:20]]
        slack('chat.postMessage', channel=canal, text='\n'.join(linhas))
        vencidas += len(venc)
    texto = relatorio(t, (datetime.now().astimezone() - __import__('datetime').timedelta(days=7)).isoformat())
    if texto and canal:
        if SECO:
            print(f'--- {t["name"]}\n{texto}')
        else:
            slack('chat.postMessage', channel=canal, text=texto, unfurl_links=False)
            relatorios += 1
print(f'issues colocadas em ciclo: {postas}; pendências vencidas avisadas: {vencidas}; relatórios: {relatorios}')
