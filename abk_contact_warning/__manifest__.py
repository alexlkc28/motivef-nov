# -*- coding: utf-8 -*-
{
    'name': "abk contact warning",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Contact will alert you when the contact is the same
if company type equals Company then compare name else company type with Individual then compare by email
    """,

    'author': "ABK",
    'website': "https://www.aboutknowledge.com/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Customizations',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'contacts', 'web'],

    # always loaded
    'data': [
        'views/views.xml'
    ],
    'assets': {

    },
}
