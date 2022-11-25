from odoo import models, fields, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    quickbook_connector_id = fields.Integer(string='Quickbook Connector ID:', default=1)
    quickbook_id = fields.Integer(string='Quickbook ID:')
    qbooks_sync_token = fields.Char(string='Sync Token')


class ResComapny(models.Model):
    _inherit = 'res.company'

    quickbook_connector_id = fields.Integer(string='Quickbook Connector ID:', default=1)


