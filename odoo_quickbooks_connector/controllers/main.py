import base64
import datetime
import requests

from odoo import http, models
from odoo.http import request


class ModelName(http.Controller):

    @http.route(['/quickbook_access'], type="http", auth="public", website=True, csrf=False)
    def example(self, **kw):
        if kw.get('code'):
            print(self,'tfygu')
            quickbooks_id = request.env.ref('odoo_quickbooks_connector.quick_data')
            print(quickbooks_id,'www')
            quickbooks_id.write({
                'quick_auth_code': kw.get('code'),
                'quick_realm_id': kw.get('realmId')
            })
            b64 = str(quickbooks_id.quick_client_id + ":" + quickbooks_id.quick_client_secret).encode('utf-8')
            b64 = base64.b64encode(b64).decode('utf-8')
            headers = {
                'Authorization': 'Basic ' + b64,
                'Accept': 'application/json',
            }
            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
            payload = {
                'code': str(kw.get('code')),
                'redirect_uri': f'{base_url}/quickbook_access',
                'grant_type': 'authorization_code'
            }
            req = requests.post(quickbooks_id.quick_access_token_url, data=payload, headers=headers)
            # print(req.json(), req.json().get('access_token'), 'wefff')
            if req.json() and req.json().get('access_token'):
                quickbooks_id.write({
                    'quick_access_token': req.json().get('access_token'),
                    'quick_refresh_token': req.json().get('refresh_token'),
                    'quick_access_token_expiry': datetime.datetime.now() + datetime.timedelta(seconds=req.json().get('expires_in')),
                    'quick_refresh_token_expiry': datetime.datetime.now() + datetime.timedelta(seconds=req.json().get('x_refresh_token_expires_in')),
                })
                action = request.env.ref('odoo_quickbooks_connector.quickbooks_connector_act_window')
                return request.redirect(f'''/web#id={quickbooks_id.id}&view_type=form&model=quickbooks.connector&action={action.id}''')
            else:
                return 'something went wrong'


