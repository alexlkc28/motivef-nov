from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    quickbook_id = fields.Integer(string='Quickbook ID', store=True)
    quickbook_connector_id = fields.Integer(string='Quick Book Connector ID', required=True, default=1)
    qbooks_sync_token = fields.Char(string='Sync Token')
    state = fields.Selection(selection_add=[('paid', 'Paid'), ('done',)])

    def button_confirm(self):
        res = super().button_confirm()
        for rec in self:
            purchase = rec
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]). \
                action_export_vendor(purchase)
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]). \
                action_export_product(purchase)
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]). \
                action_export_purchase_order(purchase)
        return res

    def button_cancel(self):
        res = super().button_cancel()
        for record in self:
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]).\
                action_delete_po(record)
        return res

    def update_order_line(self):
        for record in self:
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]).action_update_po(record)



