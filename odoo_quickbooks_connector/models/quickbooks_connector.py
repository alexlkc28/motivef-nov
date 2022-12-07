import base64
import datetime
import json

import requests

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class QuickbooksConnector(models.Model):
    _name = 'quickbooks.connector'
    _description = 'Quickbooks Connector Configuration'

    quick_auth_url = fields.Char('Authorization URL', default="https://appcenter.intuit.com/connect/oauth2")
    quick_access_token_url = fields.Char('Authorization Token URL',
                                         default="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer")
    quick_api_url = fields.Char('API URL', default="https://sandbox-quickbooks.api.intuit.com/v3/company/")
    quick_realm_id = fields.Char('Realm ID')
    quick_auth_code = fields.Char('Auth code')
    quick_access_token = fields.Char(string='Token')
    quick_client_secret = fields.Char(string='Client Secret', required=True)
    quick_client_id = fields.Char(string='Client ID', required=True)
    quick_refresh_token = fields.Char(string='Refresh token')
    quick_access_token_expiry = fields.Datetime(
        string='Access token expiry')
    quick_refresh_token_expiry = fields.Datetime(
        string='Refresh token expiry')
    quick_mode = fields.Selection(
        [('sandbox', 'Sandbox'), ('production', 'Production')], string='Mode',
        default='sandbox')
    minor_version = fields.Integer(string='Minor Version')

    invoice_paid = fields.Boolean(string='Invoice Paid/Not Paid', default=False)

    @api.onchange('quick_mode')
    def onchange_quick_mode(self):
        if self.quick_mode == 'sandbox':
            self.quick_api_url = 'https://sandbox-quickbooks.api.intuit.com/v3/company/'
        else:
            self.quick_api_url = 'https://quickbooks.api.intuit.com/v3/company/'

    def action_quickbook_auth(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        rtn_url = f'{base_url}/quickbook_access'
        url = f"""{self.quick_auth_url}?client_id={self.quick_client_id}&scope=com.intuit.quickbooks.accounting openid 
        profile email phone address&redirect_uri={rtn_url}&response_type=code&state=state"""
        self.env.company.quickbook_connector_id = self.id
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "current"
        }

    def action_refresh_token(self):
        b64 = str(
            self.quick_client_id + ":" + self.quick_client_secret).encode(
            'utf-8')
        b64 = base64.b64encode(b64).decode('utf-8')
        headers = {
            'Authorization': 'Basic ' + b64,
            'Accept': 'application/json'
        }
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.quick_refresh_token
        }
        req = requests.post(self.quick_access_token_url, headers=headers,
                            data=data)
        if req.json() and req.json().get('access_token'):
            self.write({
                'quick_access_token': req.json().get('access_token'),
                'quick_refresh_token': req.json().get('refresh_token'),
                'quick_access_token_expiry': datetime.datetime.now() + datetime.timedelta(
                    seconds=req.json().get('expires_in')),
                'quick_refresh_token_expiry': datetime.datetime.now() + datetime.timedelta(
                    seconds=req.json().get('x_refresh_token_expires_in')),
            })

    def get_import_query(self):
        if self.quick_access_token:
            headers = {
                'Authorization': 'Bearer ' + self.quick_access_token,
                'Accept': 'application/json',
                'Content-Type': 'text/plain'
            }
            request_url = self.quick_api_url + self.quick_realm_id
            return {
                'url': request_url,
                'headers': headers
            }
        else:
            return False

    def action_export_delivery_note(self, sale, stock):
        """ function that fetch all the details for creating journal entry in quickbook """

        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/journalentry?minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            sale_orders = self.env['sale.order'].search([('id', '=', sale.id)])
            for each in sale_orders:
                for line in each.order_line:
                    product = line.product_id.name
                    account = line.product_id.quick_delivery_account
                    account_id = line.product_id.quick_delivery_account_id
                    if account and account_id is False:
                        raise ValidationError('Product does not have quickbook account')
                    else:
                        price = line.price_unit
                        done = line.done_qty
                        total = done * price
                        self.create_journal_entry_data(stock, product, total, account, account_id,
                                                       req_url, headers)

    def create_journal_entry_data(self, stock, product, total, account, account_id, url, headers):
        """function for creating journal entry in quickbook"""

        req_body = {
            "Line": [
                {
                    "JournalEntryLineDetail": {
                        "PostingType": "Debit",
                        "AccountRef": {
                            "name": account,
                            "value": account_id
                        }
                    },
                    "DetailType": "JournalEntryLineDetail",
                    "Amount": total,
                    "Id": "0",
                    "Description": product
                },
                {
                    "JournalEntryLineDetail": {
                        "PostingType": "Credit",
                        "AccountRef": {
                            "name": account,
                            "value": account_id
                        }
                    },
                    "DetailType": "JournalEntryLineDetail",
                    "Amount": total,
                    "Description": product
                }
            ]
        }
        response = requests.post(url, data=json.dumps(req_body), headers=headers)
        if response.json():
            if response.json().get('JournalEntry'):
                res = response.json().get('JournalEntry')
                if 'Id' in res:
                    stock.write({
                        'quickbook_id': res.get('Id'),
                        # 'qbooks_sync_token': res.get('SyncToken')
                    })
                    self.env.cr.commit()

            elif response.json().get('fault') and response.json().get('fault').get('error')[0].get('code') == '3200':
                raise UserError(
                    _("Token expired. Kindly refresh token"))

    def delete_journal_entry(self, stock):
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/journalentry?operation=delete&minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            req_body = {
                "SyncToken": "0",
                "Id": stock.quickbook_id
            }
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)
            stock.quickbook_id = 0

    def action_export_vendor(self, purchase):
        """function for fetching the selected vendor data from PO in quickbook"""

        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/vendor?minorversion=63'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            vendor = self.env['res.partner'].search([('id', '=', purchase.partner_id.id)])
            for vendor_data in vendor:
                if vendor_data.quickbook_id == 0:
                    self.create_vendor_data(vendor_data, req_url, headers)
                else:
                    continue

    def create_vendor_data(self, vendor_data, url, headers):
        """function for creating the vendor data in quickbook"""

        req_body = {
            "DisplayName": vendor_data.name,
            "Mobile": {
                "FreeFormNumber": vendor_data.mobile
            },
            "BillAddr": {
                "City": vendor_data.city,
                "Country": vendor_data.country_id.name,
                "Line1": vendor_data.street,
                "PostalCode": vendor_data.zip,
            },
        }
        if vendor_data.parent_id:
            req_body.update({"CompanyName": vendor_data.parent_id.name})
        if vendor_data.email:
            req_body.update({"PrimaryEmailAddr": {
                "Address": vendor_data.email
            }})
        if vendor_data.phone:
            req_body.update({"PrimaryPhone": {
                "FreeFormNumber": vendor_data.phone
            }})
        if vendor_data.mobile:
            req_body.update({"PrimaryPhone": {
                "FreeFormNumber": vendor_data.mobile
            }})
        if vendor_data.vat:
            req_body.update({"TaxIdentifier": vendor_data.vat})
        if vendor_data.website:
            req_body.update({"WebAddr": {
                "URI": vendor_data.website
            }})

        response = requests.post(url, data=json.dumps(req_body), headers=headers)
        if response.json():
            if response.json().get('Vendor'):
                res = response.json().get('Vendor')
                if 'Id' in res:
                    vendor_data.write({
                        'quickbook_id': res.get('Id'),
                        'qbooks_sync_token': res.get('SyncToken')
                    })
                    self.env.cr.commit()
            elif response.json().get('Fault').get('Error')[0].get('code') == '6240':
                raise UserError(
                    _("Duplicate name exist error for %s. Quickbooks doesnot allow duplicate names. Please change name,"
                      "or please provide the quickbook ID" % vendor_data.name))
            elif response.json().get('fault') and response.json().get('fault').get('error')[0].get(
                    'code') == '3200':
                raise UserError(
                    _("Token expired. Kindly refresh token"))

    def action_export_product(self, purchase):
        """function for fetch all the data from product for importing into quickbook"""

        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/item?minorversion=4'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            for each in purchase.order_line:
                if each.product_id.quickbook_id == 0:
                    product = self.env['product.product'].search([('id', '=', each.product_id.id)])
                    desc = product.description_sale
                    self.create_product_data(product, desc, req_url, headers)
                else:
                    continue

    def create_product_data(self, product, desc, url, headers):
        """function for creating the product item in quickbook"""
        quick_type = {
            'service': 'Service',
            'consu': 'NonInventory',
            'product': 'Inventory',
        }
        if product.quickbook_income_account_id == 0:
            raise ValidationError('Please fill the income account in product form')
        if product.quickbook_asset_account_id == 0:
            raise ValidationError('Please fill the asset account in product form')
        if product.quickbook_expense_account_id == 0:
            raise ValidationError('Please fill the expense account in product form')
        req_body = {
            "Name": product.name + str(product.id),
            "Description": desc,
            "Active": True,
            "UnitPrice": product.list_price,
            "PurchaseCost": product.standard_price,
            "Type": quick_type.get(product.type),
            "PurchaseDesc": desc,
            "IncomeAccountRef": {
                "value": product.quickbook_income_account_id,
                "name": product.quickbook_income_account
            },
            "AssetAccountRef": {
                "value": product.quickbook_asset_account_id,
                "name": product.quickbook_asset_account
            },
            "ExpenseAccountRef": {
                "name": product.quickbook_expense_account,
                "value": product.quickbook_expense_account_id
            },
            "InvStartDate": "2022-03-19"
        }
        if quick_type.get(product.type) == 'Inventory':
            quantity = self.env['stock.quant'].search([]).filtered(
                lambda r: r.product_id.id == product.id and r.quantity > 0).mapped(
                'quantity')
            if quantity:
                req_body.update({"TrackQtyOnHand": True,
                                 "QtyOnHand": sum(quantity)
                                 })
            else:
                raise UserError(
                    _("Add onhand quantity for %s" % product.name))

        response = requests.post(url, data=json.dumps(req_body), headers=headers)
        if response.json():
            if response.json().get('Item'):
                res = response.json().get('Item')
                if 'Id' in res:
                    product.write({
                        'quickbook_id': res.get('Id'),
                        'qbooks_sync_token': res.get('SyncToken')
                    })
                    self.env.cr.commit()

            elif response.json().get('Fault').get('Error')[0].get('code') == '6240':
                raise UserError(
                    _("Duplicate name exist error for %s. Quickbooks doesnot allow duplicate names. Please change name,"
                      " or please provide the quickbook ID" % product.name))
            elif response.json().get('fault') and response.json().get('fault').get('error')[0].get(
                    'code') == '3200':
                raise UserError(
                    _("Token expired. Kindly refresh token"))

    def action_export_purchase_order(self, purchase):
        """ function that fetch all the details for creating purchase order in quickbook """

        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/purchaseorder?minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            purchase_order = self.env['purchase.order'].search([('id', '=', purchase.id)])
            for each in purchase_order:
                total = each.amount_total
                vendor = each.partner_id.name
                vendor_id = each.partner_id.quickbook_id
                self.create_purchase_order_data(total, vendor, vendor_id, purchase_order, req_url, headers)

    def create_purchase_order_data(self, total, vendor, vendor_id, purchase_order, url, headers):
        """ function for creating purchase order in quickbook """

        req_body = {
            "TotalAmt": total,
            "Line": [],
            "APAccountRef": {
                "name": "Accounts Payable (A/P)",
                "value": "33"
            },
            "VendorRef": {
                "name": vendor,
                "value": vendor_id
            },
        }
        for line in purchase_order.order_line:
            req_body['Line'].append(
                {
                    "DetailType": "ItemBasedExpenseLineDetail",
                    "Amount": line.price_subtotal,
                    "Id": line.id,
                    "ItemBasedExpenseLineDetail": {
                        "ItemRef": {
                            "name": line.name,
                            "value": line.product_id.quickbook_id
                        },
                        "Qty": line.product_qty,
                        "UnitPrice": line.price_unit
                    }
                }
            )
        response = requests.post(url, data=json.dumps(req_body), headers=headers)
        if response.json():
            if response.json().get('PurchaseOrder'):
                res = response.json().get('PurchaseOrder')
                if 'Id' in res:
                    purchase_order.write({
                        'quickbook_id': res.get('Id'),
                        'qbooks_sync_token': res.get('SyncToken')
                    })
                    self.env.cr.commit()

            elif response.json().get('fault') and response.json().get('fault').get('error')[0].get(
                    'code') == '3200':
                raise UserError(
                    _("Token expired. Kindly refresh token"))

    def action_delete_po(self, po):
        """function that delete the so when we cancel the
        corresponding sale order from the odoo"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/purchaseorder?operation=delete&minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            req_body = {
                "SyncToken": "0",
                "Id": po.quickbook_id,
            }
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)
            po.quickbook_id = 0

    def action_update_po(self, record):
        """function for updating the po"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/purchaseorder?minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'

            req_body = {
                "SyncToken": "0",
                "APAccountRef": {
                    "name": "Accounts Payable (A/P)",
                    "value": "33"
                },
                "CurrencyRef": {
                    "name": "United States Dollar",
                    "value": "USD"
                },
                "TotalAmt": record.amount_total,
                "Id": record.quickbook_id,
                "VendorRef": {
                    "name": record.partner_id.name,
                    "value": record.partner_id.quickbook_id
                },
                "Line": [],
            }
            for line in record.order_line:
                for product in line.product_id:
                    if product.quickbook_id is 0:
                        desc = product.description_sale
                        self.create_product_item(product, desc)
                req_body['Line'].append(
                    {
                        "DetailType": "ItemBasedExpenseLineDetail",
                        "Amount": line.price_subtotal,
                        "Id": line.id,
                        "ItemBasedExpenseLineDetail": {
                            "ItemRef": {
                                "name": line.product_id.name,
                                "value": line.product_id.quickbook_id
                            },
                            "Qty": line.product_qty,
                            "UnitPrice": line.price_unit
                        }
                    }
                )
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)

    def create_product_item(self, product, desc):
        """function that call the function that create the product item in quickbook"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/item?minorversion=4'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            self.create_product_data(product, desc, req_url, headers)

    def action_fetch_bill(self):
        """function that call the function that create the bill"""
        url = self.get_import_query()
        if url:
            query = 'SELECT * FROM Bill'
            get_url = url['url'] + f'/query?minorversion={self.minor_version}&query={query}'
            data = requests.get(get_url, headers=url['headers'])
            if data.json() and data.json().get('fault'):
                if data.json().get('fault').get('type') == 'AUTHENTICATION':
                    self.action_refresh_token()
                    data = requests.get(get_url, headers=url['headers'])

            if data.json() and data.json().get('QueryResponse'):
                bill = data.json().get('QueryResponse').get('Bill')

    def action_create_estimate(self, sale, status):
        """function that create an estimate that corresponding
        to the sale order of odoo"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/estimate?minorversion=40'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'

            if sale.partner_id.quickbook_id == 0:
                self.create_customer_data(sale.partner_id)
            for line in sale.order_line:
                if line.product_id.quickbook_id == 0:
                    desc = line.name
                    self.create_product_item(line.product_id, desc)
            req_body = {
                "TotalAmt": sale.amount_total,
                "Line": [],
                "BillEmail": {
                    "Address": sale.partner_id.email
                },
                'TxnStatus': status,
                "CustomerMemo": {
                    "value": "Thank you for your business and have a great day!"
                },
                "ShipAddr": {
                    "City": sale.partner_id.city,
                    "Line1": sale.partner_id.street,
                    "PostalCode": sale.partner_id.zip,
                },
                "BillAddr": {
                    "City": sale.partner_id.city,
                    "Line1": sale.partner_id.street,
                    "PostalCode": sale.partner_id.zip,
                },

                "CustomerRef": {
                    "name": sale.partner_id.name,
                    "value": sale.partner_id.quickbook_id
                },
            }
            for line in sale.order_line:
                req_body['Line'].append(
                    {
                        "Description": line.name,
                        "DetailType": "SalesItemLineDetail",
                        "SalesItemLineDetail": {
                            "Qty": line.product_uom_qty,
                            "UnitPrice": line.price_unit,
                            "ItemRef": {
                                "name": line.name,
                                "value": line.product_id.quickbook_id
                            }
                        },

                        "Amount": line.price_subtotal,

                    }

                )
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)
            if response.json():
                if response.json().get('Estimate'):
                    res = response.json().get('Estimate')
                    if 'Id' in res:
                        sale.write({
                            'quickbook_id': res.get('Id'),
                            'qbooks_sync_token': res.get('SyncToken')
                        })
                        self.env.cr.commit()

                elif response.json().get('fault') and response.json().get('fault').get('error')[0].get(
                        'code') == '3200':
                    raise UserError(
                        _("Token expired. Kindly refresh token"))

    def action_delete_so(self, record):
        """function that delete the so"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/estimate?operation=delete&minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            req_body = {
                "SyncToken": "0",
                "Id": record.quickbook_id,
            }
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)
            record.quickbook_id = 0

    def create_customer_data(self, customer):
        """function that helps to create a customer data in quickbook"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/customer?minorversion=40'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            if not customer.email:
                customer.email = 'demomail@gmail.com'
            if not customer.phone:
                customer.phone = '000 000 000 0'
            if not customer.city:
                customer.city = "US"
            if not customer.zip:
                customer.zip = '6666 66'
            if not customer.street:
                customer.street = 'New York'
            if not customer.country_id:
                customer.country_id.name = 'USA'
            if not customer.x_studio_customer_number:
                customer.x_studio_customer_number = '000'
            req_body = {
                "FullyQualifiedName": customer.name,
                "PrimaryEmailAddr": {
                    "Address": customer.email
                },
                "DisplayName": customer.name,
                "Notes": customer.x_studio_customer_number,
                "PrimaryPhone": {
                    "FreeFormNumber": customer.phone
                },
                "CompanyName": customer.name,
                "BillAddr": {
                    "City": customer.city,
                    "PostalCode": customer.zip,
                    "Line1": customer.street,
                    "Country": customer.country_id.name
                },
            }
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)
            if response.json():
                if response.json().get('Customer'):
                    res = response.json().get('Customer')
                    if 'Id' in res:
                        customer.write({
                            'quickbook_id': res.get('Id'),
                            'qbooks_sync_token': res.get('SyncToken')
                        })
                        self.env.cr.commit()

                elif response.json().get('fault') and response.json().get('fault').get('error')[0].get(
                        'code') == '3200':
                    raise UserError(
                        _("Token expired. Kindly refresh token"))

    def create_and_sync_invoices(self, invoice, sale):
        """function that helps to create the invoice in quickbook"""
        if not sale.quickbook_id == 0:
            url = self.get_import_query()
            if url:
                req_url = f'{url["url"]}/invoice?minorversion=65'
                headers = url.get('headers')
                headers['Content-Type'] = 'application/json'
                customer = invoice.partner_id.name
                customer_code = invoice.partner_id.quickbook_id
                req_body = {
                    "Line": [],
                    "CustomerRef": {
                        "name": customer,
                        "value": customer_code
                    }
                }
                for line in invoice.invoice_line_ids:
                    amount = line.price_subtotal
                    if line.product_id:
                        if line.product_id.quickbook_id == 0:
                            self.create_product_item(line.product_id, line.name)
                        item_name = line.product_id.name
                        item_code = line.product_id.quickbook_id
                        req_body['Line'].append(
                            {
                                "DetailType": "SalesItemLineDetail",
                                "Amount": amount,
                                "SalesItemLineDetail": {
                                    "ItemRef": {
                                        "name": item_name,
                                        "value": item_code
                                    }
                                }
                            }
                        )

                response = requests.post(req_url, data=json.dumps(req_body), headers=headers)
                if response.json():
                    if response.json().get('Invoice'):
                        res = response.json().get('Invoice')
                        if 'Id' in res:
                            invoice.write({
                                'quickbook_id': res.get('Id'),
                                'qbooks_sync_token': res.get('SyncToken')
                            })
                            self.env.cr.commit()

                    elif response.json().get('fault') and response.json().get('fault').get('error')[0].get(
                            'code') == '3200':
                        raise UserError(
                            _("Token expired. Kindly refresh token"))

    def sale_order_status_updation(self, sales):
        """function helps to update the sale order"""
        for sale in sales:
            self.delete_the_current_so(sale)
            status = 'Closed'
            self.action_create_estimate(sale, status)

    def delete_the_current_so(self, sale):
        """function helps to delete the current so"""
        url = self.get_import_query()
        if url:
            req_url = f'{url["url"]}/estimate?operation=delete&minorversion=65'
            headers = url.get('headers')
            headers['Content-Type'] = 'application/json'
            req_body = {
                "SyncToken": "3",
                "Id": sale.quickbook_id
            }
            response = requests.post(req_url, data=json.dumps(req_body), headers=headers)

    def action_export_invoice_status(self):
        """this function is helps to updates the invoice status in odoo.
         also it helps to update the status of estimate in quickbook"""
        url = self.get_import_query()
        print(url, 'urrrrl')
        if url:
            query = 'select * from Invoice'
            get_url = url['url'] + f'/query?minorversion={self.minor_version}&query={query}'
            data = requests.get(get_url, headers=url['headers'])
            invoice_odoo = self.env['account.move'].search([('quickbook_id', '!=', 0)])
            if data.json() and data.json().get('fault'):
                if data.json().get('fault').get('type') == 'AUTHENTICATION':
                    self.action_refresh_token()
                    data = requests.get(get_url, headers=url['headers'])
            if data.json() and data.json().get('QueryResponse'):
                invoices_quickbook = data.json().get('QueryResponse').get('Invoice')
                for invoice in invoice_odoo:
                    for invoice_q in invoices_quickbook:
                        # print(invoice_q, 'idcdsvb')
                        qbinvoice_id = int(invoice_q['Id'])
                        if invoice.quickbook_id == qbinvoice_id:
                            if invoice_q['LinkedTxn']:
                                for txn_type in invoice_q['LinkedTxn']:
                                    if txn_type['TxnType'] == 'Payment':
                                        if invoice.state != 'posted':
                                            invoice.action_post()
                                            invoice.state = 'posted'
                                        if invoice.payment_state != 'paid':
                                            invoice.payment_state = 'paid'
                                            self.invoice_paid = True
                                        sale = self.env['sale.order'].search([('name', '=', invoice.invoice_origin)])
                                        for each in sale.invoice_ids:
                                            if each.payment_state != 'paid':
                                                self.invoice_paid = False
                                            else:
                                                self.invoice_paid = True

                                        if self.invoice_paid != False:
                                            self.sale_order_status_updation(sale)
                                            self.action_export_payment_status()

    def action_fetch_payment_methods(self):
        """function to get the payment methods and its
        id's from quickbook to odoo payment method"""
        url = self.get_import_query()
        if url:
            query = 'select * from PaymentMethod'
            get_url = url['url'] + f'/query?minorversion={self.minor_version}&query={query}'
            data = requests.get(get_url, headers=url['headers'])
            total = 0
            payment_method_obj = self.env['account.payment.method'].search([])
            if data.json() and data.json().get('fault'):
                if data.json().get('fault').get('type') == 'AUTHENTICATION':
                    self.action_refresh_token()
                    data = requests.get(get_url, headers=url['headers'])
            if data.json() and data.json().get('QueryResponse'):
                payment_method_quickbook = data.json().get('QueryResponse').get('PaymentMethod')
                print(payment_method_quickbook, 'aaaaa')
                for payment_method in payment_method_quickbook:
                    exist = payment_method_obj.search([('quick_id', '=', payment_method.get('Id'))])
                    if exist:
                        continue
                    payment_vals = {
                        'quick_id': payment_method.get('Id'),
                        'name': payment_method.get('Name'),
                        'payment_type': 'inbound',
                        'code': 'manual',
                    }
                    print(payment_vals, 'payyy')
                    payment_method_obj.create(payment_vals)

    def action_export_payment_status(self):
        """this function is helps to updates the invoice status in odoo.
         also it helps to update the status of estimate in quickbook"""
        url = self.get_import_query()
        if url:
            query = 'select * from Payment'
            get_url = url['url'] + f'/query?minorversion={self.minor_version}&query={query}'
            data = requests.get(get_url, headers=url['headers'])
            total = 0
            if data.json() and data.json().get('fault'):
                if data.json().get('fault').get('type') == 'AUTHENTICATION':
                    self.action_refresh_token()
                    data = requests.get(get_url, headers=url['headers'])
            if data.json() and data.json().get('QueryResponse'):
                payment_quickbook = data.json().get('QueryResponse').get('Payment')
                for payment in payment_quickbook:
                    print(payment)
                    payment_ref = payment.get('PaymentRefNum')
                    payment_method_ref = payment.get('PaymentMethodRef')
                    if payment_method_ref and payment_ref:
                        pay_ref = payment_ref
                        pay_method = payment_method_ref['value']
                        pay_m = self.env['account.payment.method'].search([('quick_id', '=', int(pay_method))])
                        LineTxn = payment.get('Line')
                        if LineTxn:
                            for each in LineTxn:
                                txn_details = each['LinkedTxn']
                                if txn_details:
                                    for txn in txn_details:
                                        if txn['TxnType'] == 'Invoice':
                                            txn_id = txn['TxnId']
                                            print(txn_id)
                                            inv = self.env['account.move'].search([('quickbook_id', '=', int(txn_id))])
                                            print(inv)
                                            inv.quick_memo = str(pay_ref) + ' ' + str(pay_m.name)
