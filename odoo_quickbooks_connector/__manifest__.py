{
    'name': 'Odoo Quickbooks Connector',
    'version': '14.0.1.0.0',
    'summary': 'Allow users to connect odoo and  Quickbooks',
    'author': "ABK",
    'website': "https://www.aboutknowledge.com/",
    'depends': ['base', 'sale', 'stock', 'account', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/quickbooks_connector_view.xml',
        'views/sale_order.xml',
        'views/purchase_order.xml',
        'views/res_partner_view.xml',
        'views/views.xml',
        'views/report_synced_quickbook.xml',
        'data/quickbooks_connector_data.xml',
        'data/crone_schedule_for_sync_to_qb.xml',
    ],

    'installable': True,
    'auto_install': False,
}
