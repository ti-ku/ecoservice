# -*- encoding: utf-8 -*-
""" The account module extends the original OpenERP account objects with different attributes and methods
"""
##############################################################################
#    ecoservice_financeinterface_datev
#    Copyright (c) 2013 ecoservice GbR (<http://www.ecoservice.de>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    This program based on OpenERP.
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
##############################################################################
from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp.tools import ustr
from openerp import models
from decimal import Decimal

class AccountAccount(models.Model):
    """Inherits the account.account class and adds attributes
    """
    _inherit = "account.account"
    _columns = {
                'ustuebergabe': fields.boolean('Datev UST-ID', help=_("""Is required when transferring 
                a sales tax identification number  from the account partner (e.g. EU-Invoice)""")),
                'automatic':fields.boolean('Datev Automatikkonto'),
                'datev_steuer': fields.many2one('account.tax','Datev Steuerkonto'),
                'datev_steuer_erforderlich':fields.boolean('Steuerbuchung erforderlich?'),
    }
    _defaults = {
                 'ustuebergabe': lambda * a: False,
    }
    
    def cron_update_line_autoaccounts_tax(self,cr, uid):
        """Method for Cronjop that Updates all account.move.lines 
        without ecofi_taxid of Accounts where automatic is True and a datev_steuer
        """
        ids = self.search(cr, uid, [('automatic', '=', True), ('datev_steuer', '!=', False )])
        for account in self.read(cr, uid, ids, load='_classic_write'):
            move_line_ids = self.pool.get('account.move.line').search(cr, uid, [('account_id', '=', account['id']), ('ecofi_taxid','=', False)])
            if move_line_ids:
                self.pool.get('account.move.line').write(cr, uid, move_line_ids, {'ecofi_taxid': account['datev_steuer']})
            
AccountAccount()

class AccountTax(models.Model):
    """Inherits the account.tax class and adds attributes
    """
    _inherit = 'account.tax'
    _columns = {
                'datev_skonto': fields.many2one('account.account','Datev Skontokonto'),
    }
AccountTax()


class AccountPaymentTerm(models.Model):
    """Inherits the account.payment.term class and adds attributes
    """
    _inherit = "account.payment.term"
    _columns = {
                'zahlsl': fields.integer('Payment key'),
    }
AccountPaymentTerm()

class AccountMove(models.Model):
    """ Inherits the account.move class to add checkmethods to the original post methode
    """
    _inherit = "account.move"

    def datev_account_checks(self, cr, uid, move, context={}):
        error = ''
        linecount = 0
        self.update_line_autoaccounts_tax(cr, uid, move, context=context)
        for line in move.line_ids:
            linecount += 1
            if line.account_id.id != line.ecofi_account_counterpart.id:
                if not self.pool.get('ecofi').is_taxline(cr, line.account_id.id) or line.ecofi_bu == 'SD':
                    linetax = self.pool.get('ecofi').get_line_tax(cr, uid, line)
                    if line.account_id.automatic is True and not line.account_id.datev_steuer:
                        error += _("""The account %s is an Autoaccount, although the automatic taxes are not configured!\n""") % (line.account_id.code)                        
                    if line.account_id.datev_steuer_erforderlich is True and linetax is False:
                        error += _("""The Account requires a tax, although the moveline %s has no tax!\n""") % (linecount)
                    if line.account_id.automatic is True and linetax:
                        if line.account_id.datev_steuer:
                            if linetax.id != line.account_id.datev_steuer.id:
                                error += _("""The account is an Autoaccount, altough the taxaccount (%s) in the moveline %s is an other than the configured %s!\n""") % (linecount,
                                                        linetax.name, line.account_id.datev_steuer.name)
                        else:
                            if linetax != False:
                                error += _("""The account is an Autoaccount, altough the taxaccount (%s) in the moveline %s is an other than the configured %s!\n""") % (linecount,
                                                        linetax.name, line.account_id.datev_steuer.name)
                    if line.account_id.automatic is True and linetax is False:
                        error += _("""The account is an Autoaccount, altough the taxaccount in the moveline %s is not set!\n""") % (linecount)                        
                    if line.account_id.automatic is False and linetax and linetax.buchungsschluessel < 0:  # pylint: disable-msg=E1103
                        error += _(ustr("""The bookingkey for the tax %s is not configured!\n""")) % (linetax.name)  # pylint: disable-msg=E1103,C0301
        return error
    
    def update_line_autoaccounts_tax(self, cr, uid, move, context={}):
        error = ''
        linecount = 0
        for line in move.line_ids:
            linecount += 1
            if line.account_id.id != line.ecofi_account_counterpart.id:
                if not self.pool.get('ecofi').is_taxline(cr, line.account_id.id):
                    linetax = self.pool.get('ecofi').get_line_tax(cr, uid, line)
                    if line.account_id.automatic is True and linetax is False:
                        if line.account_id.datev_steuer:
                            self.pool.get('account.move.line').write(cr, uid, [line.id], {'ecofi_taxid': line.account_id.datev_steuer.id}, context=context)
                        else:
                            error += _("""The Account is an Autoaccount, although the moveline %s has no tax!\n""") % (linecount)
        return error

    def datev_tax_check(self, cr, uid, move, context={}):
        error = ''
        linecount = 0
        tax_values = {}
        linecounter = 0
        for line in move.line_ids:
            linecount += 1
            if line.account_id.id != line.ecofi_account_counterpart.id:
                if self.pool.get('ecofi').is_taxline(cr, line.account_id.id) and not line.ecofi_bu == 'SD':
                    if line.account_id.code not in tax_values:
                        tax_values[line.account_id.code] = {'real': 0.00,
                                                         'datev': 0.00,
                                                         }
                    tax_values[line.account_id.code]['real'] += line.debit - line.credit 
                else:
                    linecounter += 1
                    new_context = context.copy()
                    new_context['return_calc'] = True
                    taxcalc_ids = self.pool.get('ecofi').calculate_tax(cr, uid, line, new_context)
                    for taxcalc_id in taxcalc_ids:
                        taxaccount = taxcalc_id['refund_account_id'] and taxcalc_id['refund_account_id'] or taxcalc_id['account_id']
                        if taxaccount:
                            datev_account_code = self.pool.get('account.account').read(cr, uid, taxaccount, context=new_context)['code']           
                            if datev_account_code not in tax_values:
                                tax_values[datev_account_code] = {'real': 0.00,
                                                                 'datev': 0.00,
                                                                 }
                            if line.ecofi_bu and line.ecofi_bu == '40':
                                continue
                            tax_values[datev_account_code]['datev'] += taxcalc_id['amount']
        for tax in tax_values:
            if Decimal(str(abs(tax_values[tax]['real'] - tax_values[tax]['datev']))) > Decimal(str(10 ** -2 * linecounter)):
                error += _("""The Value for the tax on taxaccount %s is different between booked %s and calculated %s!\n""" % (tax, tax_values[tax]['real'], tax_values[tax]['datev']))
        return error        
     
    def datev_checks(self, cr, uid, move, context={}):
        """Constraintcheck if export method is 'brutto'
        :param cr: the current row, from the database cursor
        :param uid: the current user’s ID for security checks
        :param move: account_move
        :param ecofikonto: main account of the move
        :param context: context arguments, like lang, time zone
        """
        error = ''
        error += self.update_line_autoaccounts_tax(cr, uid, move, context=context)
        error += self.datev_account_checks(cr, uid, move, context=context)
        if error == '':
            error += self.datev_tax_check(cr, uid, move, context=context)
        if error == '':
            return False
        return error

    def finance_interface_checks(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        res = super(AccountMove, self).finance_interface_checks(cr, uid, ids, context=context)
        for move in self.browse(cr, uid, ids, context=context):
            thiserror = ''
            error = self.datev_checks(cr, uid, move, context)
            if error:
                raise osv.except_osv('Error', error)
        return res

AccountMove()

class AccountMoveLine(models.Model):
    """Inherits the account.move.line class and adds attributes
    """
    _inherit = "account.move.line"
    _columns = {
                'ecofi_bu': fields.selection([
                    ('40', '40'),
                    ('SD', 'Steuer Direkt'),
                    ], 'Datev BU', select=True),
                }
AccountMoveLine()
