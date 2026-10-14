"""Job semanal: põe no ciclo as issues com prazo ainda sem ciclo e avisa pendências externas vencidas.

Lê LINEAR_API_KEY e SLACK_BOT_TOKEN do ambiente. Imprime só contagens (o log é público).
"""
import json, os, re, unicodedata, urllib.request
from datetime import date, datetime

def post(url, corpo, auth):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={'Content-Type': 'application/json; charset=utf-8', 'Authorization': auth})
    return json.load(urllib.request.urlopen(req, timeout=60))

def gql(q, v=None):
    d = post('https://api.linear.app/graphql', {'query': q, 'variables': v or {}}, os.environ['LINEAR_API_KEY'])
    if d.get('errors'): raise SystemExit('erro na API do Linear')
    return d['data']

def slack(metodo, **kw):
    return post('https://slack.com/api/' + metodo, kw, 'Bearer ' + os.environ['SLACK_BOT_TOKEN'])

def slug(t):
    t = unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')

dia = lambda s: datetime.fromisoformat(s.replace('Z', '+00:00')).date()
hoje = date.today()
postas, vencidas = 0, 0
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
            if alvo:
                gql('mutation($id:String!,$i:IssueUpdateInput!){ issueUpdate(id:$id,input:$i){ success } }', {'id': i['id'], 'i': {'cycleId': alvo[2]}})
                postas += 1
        if p < hoje and any(l['name'] == 'Pendência externa' for l in i['labels']['nodes']):
            venc.append(i)
    canal = canais.get('proj-' + slug(t['name']))
    if venc and canal:
        linhas = [f':warning: *{len(venc)} pendência(s) externa(s) vencida(s) em {t["name"]}*'] + [f'• <{i["url"]}|{i["title"]}> (prazo {i["dueDate"]})' for i in venc[:20]]
        slack('chat.postMessage', channel=canal, text='\n'.join(linhas))
        vencidas += len(venc)
print(f'issues colocadas em ciclo: {postas}; pendências vencidas avisadas: {vencidas}')
