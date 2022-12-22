import base64

from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    quickbook_id = fields.Integer(string='Quickbook ID')
    return_delivery = fields.Boolean(string='Return', store=True)

    def action_validate_button(self):

        sale = self.env['sale.order'].search([('picking_ids', '=', self.id)])
        stock = self
        if self.return_delivery == True:
            self.env['quickbooks.connector'].search(
                [('id', '=', self.env.company.quickbook_connector_id)]).delete_journal_entry(stock)
        else:
            for each in self.move_line_ids_without_package:
                product = each.product_id
                qty = each.qty_done
                for rec in sale.order_line:
                    rec.done_qty = qty
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]).action_export_delivery_note(sale, stock)

        return


class StockBackorderConfirmation(models.TransientModel):
    _inherit = 'stock.backorder.confirmation'

    def process(self):
        pickings_to_do = self.env['stock.picking']
        pickings_not_to_do = self.env['stock.picking']
        for line in self.backorder_confirmation_line_ids:
            if line.to_backorder is True:
                pickings_to_do |= line.picking_id
            else:
                pickings_not_to_do |= line.picking_id

        for pick_id in pickings_not_to_do:
            moves_to_log = {}
            for move in pick_id.move_lines:
                if float_compare(move.product_uom_qty,
                                 move.quantity_done,
                                 precision_rounding=move.product_uom.rounding) > 0:
                    moves_to_log[move] = (move.quantity_done, move.product_uom_qty)
            pick_id._log_less_quantities_than_expected(moves_to_log)

        pickings_to_validate = self.env.context.get('button_validate_picking_ids')
        if pickings_to_validate:
            pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate).with_context(skip_backorder=True)
            if pickings_not_to_do:
                pickings_to_validate = pickings_to_validate.with_context(picking_ids_not_to_backorder=pickings_not_to_do.ids)
            pickings_to_validate.action_validate_button()
            return pickings_to_validate.button_validate()
        return True

    def process_cancel_backorder(self):
        pickings_to_validate = self.env.context.get('button_validate_picking_ids')
        if pickings_to_validate:
            self.env['stock.picking'].browse(pickings_to_validate) \
                .with_context(skip_backorder=True, picking_ids_not_to_backorder=self.pick_ids.ids) \
                .action_validate_button()
            return self.env['stock.picking']\
                .browse(pickings_to_validate)\
                .with_context(skip_backorder=True, picking_ids_not_to_backorder=self.pick_ids.ids)\
                .button_validate()
        return True


class StockImmediatePicking(models.TransientModel):
    _inherit = 'stock.immediate.transfer'

    def process(self):
        pickings_to_do = self.env['stock.picking']
        pickings_not_to_do = self.env['stock.picking']
        for line in self.immediate_transfer_line_ids:
            if line.to_immediate is True:
                pickings_to_do |= line.picking_id
            else:
                pickings_not_to_do |= line.picking_id

        for picking in pickings_to_do:
            # If still in draft => confirm and assign
            if picking.state == 'draft':
                picking.action_confirm()
                if picking.state != 'assigned':
                    picking.action_assign()
                    if picking.state != 'assigned':
                        raise UserError(_("Could not reserve all requested products. Please use the \'Mark as Todo\'"
                                          " button to handle the reservation manually."))
            for move in picking.move_lines.filtered(lambda m: m.state not in ['done', 'cancel']):
                for move_line in move.move_line_ids:
                    move_line.qty_done = move_line.product_uom_qty

        pickings_to_validate = self.env.context.get('button_validate_picking_ids')
        if pickings_to_validate:
            pickings_to_validate = self.env['stock.picking'].browse(pickings_to_validate)
            pickings_to_validate = pickings_to_validate - pickings_not_to_do
            pickings_to_validate.with_context(skip_immediate=True).action_validate_button()
            return pickings_to_validate.with_context(skip_immediate=True).button_validate()
        return True


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    done_qty = fields.Float(string='Done')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    quickbook_id = fields.Integer(string='Quickbook ID', help="This id represents the Quickbook Account ID")
    quickbook_connector_id = fields.Integer(string='Quickbook Connector ID',
                                            help="The id represents the quickbook connector id", default=1)
    qbooks_sync_token = fields.Char(string='Sync Token')
    quick_product_id = fields.Integer(string='Product ID')

    # def action_confirm(self):
    #     res = super(SaleOrder, self).action_confirm()
    #     for rec in self:
    #         sale = rec
    #         status = 'Pending'
    #         self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]). \
    #             action_create_estimate(sale, status)
    #     return res

    # def action_cancel(self):
    #     res = super().action_cancel()
    #     for record in self:
    #         self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]). \
    #             action_delete_so(record)
    #     return res


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    quick_delivery_account = fields.Char(string='QuickBook Delivery Account',
                                         help='This Account is used for creating the journal entry')
    quick_delivery_account_id = fields.Integer(string='QuickBook Delivery Account ID', default=32)
    quickbook_id = fields.Integer(string="QuickBook ID")
    quickbook_income_account = fields.Char(string='Quickbook Income Account',
                                           help='This account is the expense account for the product in quickbook')
    quickbook_income_account_id = fields.Integer(string="Quickbook Income Account ID", default=32)
    quickbook_expense_account = fields.Char(string='Quickbook Expense Account',
                                            help='this account is expense account for the product in quickbook')
    quickbook_expense_account_id = fields.Integer(string='Quickbook Expense Account ID', default=32)
    quickbook_asset_account = fields.Char(string='Quickbook Asset Account',
                                          help='This account is the asset account for the product in quickbook')
    quickbook_asset_account_id = fields.Integer(string='Quickbook Asset Account ID', default=32)
    qbooks_sync_token = fields.Char(string='Sync Token')
    # is_quickbook_product = fields.Boolean(string='From QB', default=False)


class AccountMove(models.Model):
    _inherit = 'account.move'

    quickbook_id = fields.Integer(string='Quickbook ID')
    qbooks_sync_token = fields.Char(string='Quickbook Token')
    quick_memo = fields.Char(string='Memo')
    quick_product_id = fields.Integer(string='Product ID')

    def button_invoice_sync_qb(self):
        invoice = self
        sale = self.env['sale.order'].search([('name', '=', invoice.invoice_origin)])
        if invoice.quickbook_id == 0:
            print('lloo')
            self.env['quickbooks.connector'].search([('id', '=', self.env.company.quickbook_connector_id)]). \
                create_and_sync_invoices(invoice, sale)


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def create_returns(self):
        res = super(StockReturnPicking, self).create_returns()
        stocks = self.env['stock.picking'].search([('group_id', '=', self.picking_id.group_id.id)])
        for each in stocks:
            each.return_delivery = True
        return res


class AccountPaymentMethod(models.Model):
    _inherit = 'account.payment.method'

    quick_id = fields.Integer(string='Quickbook Id')


class ResCompany(models.Model):
    _inherit = 'res.company'

    receiver = fields.Char(string='Receive To')
    purchase_count = fields.Integer(string='Total No.of PO synced: ', compute='_compute_count_synced_qb')
    purchase_failed = fields.Integer(string='Failed Purchase: ', compute='_compute_count_synced_qb')
    invoice_count = fields.Integer(string='Total No.of invoices Synced: ', compute='_compute_count_synced_qb')
    invoice_failed = fields.Integer(string='Failed Invoice', compute='_compute_count_synced_qb')
    journal_count = fields.Integer(string='Entries Created', compute='_compute_count_synced_qb')
    journal_failed = fields.Integer(string='Failed Entries', compute='_compute_count_synced_qb')
    template_id = fields.Many2one('mail.template', string='Email Template', domain="[('model','=','customer.report')]",
                                  required=True)

    def _compute_count_synced_qb(self):
        self.purchase_count = 0
        self.invoice_count = 0
        self.invoice_failed = 0
        self.purchase_failed = 0
        for rec in self:
            rec.purchase_count = self.env['purchase.order'].search_count([('quickbook_id', '!=', 0)])
            rec.purchase_failed = self.env['purchase.order'].search_count([('quickbook_id', '=', 0)])
            rec.journal_count = self.env['stock.picking'].search_count([('quickbook_id', '!=', 0)])
            rec.journal_failed = self.env['stock.picking'].search_count([('quickbook_id', '=', 0)])
            print(rec.purchase_count)
            invoice = self.env['account.move'].search([])
            rec.invoice_count = invoice.search_count([('quickbook_id', '!=', 0)])
            rec.invoice_failed = invoice.search_count([('quickbook_id', '=', 0)])
    def send_email_with_synced_report(self):
        print('hii')
        self.env['mail.mail'].sudo().create({
            'email_from': 'democompany74@gmail.com',
            'author_id': self.env.user.partner_id.id,
            'body_html': 'Hello this mail is to show that the quickbook success and failure rate.<br>'
                         '<table border="1">'
                         '<thead>'
                         '<tr>'
                         '<th>No.of Invoice Synced</th>'
                         '<th>No.of PO Synced</th>'
                         '<th>No.of Entries created</th>'
                         '</tr>'
                         '</thead>'
                         '<tbody>'
                         '<tr>'
                         '<td>%s</td>'
                         '<td>%s</td>'
                         '<td>%s</td>'
                         '</tr>'
                         '</tbody>'
                         '</table>'%(self.invoice_count, self.purchase_count, self.invoice_count),
            'subject': 'Quickbook Sync History',
            'email_to': self.receiver
        }).send(auto_commit=False)

    def print_reprt(self):
        # return self.env.ref('odoo_quickbooks_connector.custom_report_pdf_report').report_action(self)
        report_template_id = self.env.ref(
            'odoo_quickbooks_connector.custom_report_pdf_report')._render_qweb_pdf(self.id)
        data_record = base64.b64encode(report_template_id[0])
        ir_values = {
            'name': "Quckbook Report",
            'type': 'binary',
            'datas': data_record,
            'store_fname': data_record,
            'mimetype': 'application/x-pdf',
        }
        data_id = self.env['ir.attachment'].create(ir_values)
        template = self.template_id
        template.attachment_ids = [(6, 0, [data_id.id])]
        email_values = {'email_to': self.receiver,
                        'email_from': 'democompany74@gmail.com'}
        template.send_mail(self.id, email_values=email_values, force_send=True)
        template.attachment_ids = [(3, data_id.id)]
        return True
