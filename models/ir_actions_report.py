# Part of Odoo. See LICENSE file for full copyright and licensing details.
import io
from odoo import models
from odoo.tools.parse_version import parse_version
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter, to_pdf_stream

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        # OVERRIDE
        res = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids)
        report = self._get_report(report_ref)
        if not res_ids or report.report_name != 'account_followup.report_followup_print_all':
            return res

        # TODO: Remove this check in master
        # This makes sure the report template is upgraded to a version compatible with this function.
        # Note: field latest_version of model ir.module.module is the installed version
        installed_module_version = self.sudo().env.ref('base.module_account_followup').latest_version
        if parse_version(installed_module_version)[2:] < parse_version('1.1'):
            return res

        options = data.get('options', {})
        for partner_id in res_ids:
            partner = self.env['res.partner'].browse(partner_id)
            join_invoices = options.get('join_invoices', partner.followup_line_id.join_invoices)
            if not join_invoices:
                continue

            if options.get('attachment_ids'):
                attachments = self.env['ir.attachment'].browse(options.get('attachment_ids'))
            else:
                invoices = partner._get_invoices_to_print(options)
                pdf_attachments = []
                
                # Get or generate PDF for each invoice
                for invoice in invoices:
                    # First try to find an existing PDF attachment for this invoice
                    existing_pdf = self.env['ir.attachment'].search([
                        ('res_model', '=', invoice._name),
                        ('res_id', '=', invoice.id),
                        ('mimetype', '=', 'application/pdf'),
                    ], limit=1)
                    
                    if existing_pdf:
                        pdf_attachments.append(existing_pdf)
                    else:
                        # Generate new PDF if none exists
                        pdf_content = invoice._render_qweb_pdf()[0]
                        attachment = self.env['ir.attachment'].create({
                            'name': f"{invoice.name}.pdf",
                            'type': 'binary',
                            'datas': pdf_content,
                            'mimetype': 'application/pdf',
                            'res_model': invoice._name,
                            'res_id': invoice.id,
                            'description': 'Generated PDF for followup email'  # Mark it as generated for followup
                        })
                        pdf_attachments.append(attachment)
                
                attachments = pdf_attachments

            writer = OdooPdfFileWriter()

            # Only include the invoice PDFs
            input_streams = [to_pdf_stream(attachment) for attachment in attachments
                            if attachment.mimetype == 'application/pdf']
            for stream in input_streams:
                reader = OdooPdfFileReader(stream, strict=False)
                writer.appendPagesFromReader(reader)

            # Generate the output stream from writer and close the input streams
            output_stream = io.BytesIO()
            writer.write(output_stream)
            res[partner_id]['stream'] = output_stream
            for stream in input_streams:
                stream.close()

        return res
