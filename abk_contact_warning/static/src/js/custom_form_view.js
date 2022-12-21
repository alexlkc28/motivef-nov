odoo.define('custom_form_view.contact_form', function (require) {
'use strict';

    var viewRegistry = require('web.view_registry');
    var FormController = require('web.FormController');
    var FormView = require('web.FormView');
    var Dialog = require('web.Dialog');
    var core = require('web.core');
    var rpc = require('web.rpc');

    var ContactFormController = FormController.extend({
        saveRecord: function (recordID, options) {
            var _super = this._super.bind(this);
            var _t = core._t;

            var model = this.model.get(recordID || this.handle);
            if (model.data && model.data.id) {
                return this._super.apply(this, arguments);
            }

            var company_type = $('input[type="radio"][checked=true]').attr('data-value');
            var domain = [];
            if (company_type == 'company'){
                var name = $('input[name="name"]').val();
                console.log('1-company');
                if (!name) {
                console.log('3')
                    return this._super.apply(this, arguments);
                }
                domain = [['name', '=', name]];
            } else {
                var email = $('input[name="email"]').val();
                console.log('2-person');
                if (!email) {
                    return this._super.apply(this, arguments);
                }
                domain = [['email', '=', email]];
            }

            rpc.query({
                model: 'res.partner',
                method: 'search',
                args: [domain]
            }).then(function (contacts) {
                console.log(contacts);
                if (contacts.length > 0) {
                    new Dialog(this, {
                        title: _t("Warning"),
                        $content: $('<div/>') .append($('<p/>', {text: _t("Duplicate Contact")})),
                        buttons: [
                            {
                                text: _t("Ok"),
                                classes: 'btn btn-primary',
                                click: function() {
                                    this.close();
                                    return _super(recordID, options);
                                },
                                close: true
                            }, {
                                text: _t('Cancel'),
                                close: true
                            }
                        ]
                    }).open();
        
                    return Promise.reject("SaveRecord: waiting for check duplicate");
                }

                return _super(recordID, options);
            });

            return Promise.reject("SaveRecord: waiting for check duplicate");
        },
    });

    var ContactFormView = FormView.extend({
        config: _.extend({}, FormView.prototype.config, {
            Controller: ContactFormController,
        }),
    });

    viewRegistry.add('res_partner_form', ContactFormView);

});