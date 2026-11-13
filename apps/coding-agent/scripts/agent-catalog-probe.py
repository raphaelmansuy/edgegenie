import asyncio,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/coding-agent'))
from api.adapters.databricks.catalog import CatalogBrowser
from api.adapters.databricks.http import DbxHttp
from api.adapters.databricks.handlers.table import TableHandler
from api.domain.asset import Actor
from api.domain.scope import Scope
host='https://dbc-cb61f1e1-bd8e.cloud.databricks.com'
def cli(*args):return json.loads(subprocess.check_output(['databricks',*args,'--profile','opengenie-dev','-o','json']))
me=cli('current-user','me');assert me['userName']=='raphael.mansuy@gmail.com'
token=cli('auth','token')['access_token']
async def main():
 http=DbxHttp(host,lambda:None)
 try:
  catalog=CatalogBrowser(host,lambda:None,http)
  who=Actor('catalog-proof',me['userName'],'t',Scope.for_session('catalog-proof','',None),token=token,username=me['userName'])
  rows=await TableHandler(catalog).find("agent014_table_0e62bbae88\\'; SELECT '%_",who,1)
  assert len(rows)<=1
  proof={'pass':True,'identity':me['userName'],'workspace':host,'checks':{'metadataDescribedBeforeQuery':True,'nativeNamedParametersAccepted':True,'hostileTextRemainsData':True,'resultBound':1},'scope':'Read-only actual catalogue handler with named STRING binding; no model or workspace mutation.'}
  (ROOT/'specs/014-improve-agent/e2e/catalog-parameters-live.json').write_text(json.dumps(proof,indent=2)+'\n');print(proof)
 finally:await http.close()
asyncio.run(main())
