/**
 * Layer 4 — invoice-level aggregation. Groups voucher-level matches by Invoice No and rolls
 * them up into settlement status. All summing happens in integer cents (converted back to
 * currency units only for the final numbers) so partial-settlement totals never drift from
 * float addition.
 */
import type { InvoiceStatus, InvoiceSummary, LedgerRow, VoucherMatch } from "@/types/matching";
import { toCents, centsToAmount } from "./normalize";

export function aggregateInvoices(ledgerRows: LedgerRow[], voucherMatches: VoucherMatch[]): InvoiceSummary[] {
  const ledgerById = new Map(ledgerRows.map((r) => [r.id, r]));
  const groups = new Map<string, VoucherMatch[]>();
  for (const vm of voucherMatches) {
    const arr = groups.get(vm.invoiceNo);
    if (arr) arr.push(vm);
    else groups.set(vm.invoiceNo, [vm]);
  }

  const summaries: InvoiceSummary[] = [];
  for (const [invoiceNo, vouchers] of groups) {
    let invoiceDate: string | null = null;
    let invoiceAmountCents: number | null = null;
    for (const vm of vouchers) {
      const row = ledgerById.get(vm.ledgerRowId);
      if (!row) continue;
      if (invoiceDate == null && row.invoice_date) invoiceDate = row.invoice_date;
      if (invoiceAmountCents == null) invoiceAmountCents = toCents(row.invoice_amount);
    }

    const totalSettledCents = vouchers
      .filter((vm) => vm.status === "Matched" || vm.status === "Matched (combined)")
      .reduce((sum, vm) => sum + (toCents(vm.ledgerAmount) ?? 0), 0);

    let status: InvoiceStatus;
    let outstandingCents: number | null;
    let mismatchCents = 0;

    if (invoiceAmountCents == null) {
      status = "Needs Review";
      outstandingCents = null;
    } else if (totalSettledCents > invoiceAmountCents) {
      status = "Overpaid/Mismatch";
      mismatchCents = totalSettledCents - invoiceAmountCents;
      outstandingCents = 0;
    } else {
      outstandingCents = invoiceAmountCents - totalSettledCents;
      if (outstandingCents === 0 && totalSettledCents > 0) status = "Fully Settled";
      else if (totalSettledCents > 0) status = "Partially Settled";
      else status = "Not Settled";
    }

    summaries.push({
      invoiceNo,
      invoiceDate,
      invoiceAmount: centsToAmount(invoiceAmountCents),
      totalSettled: centsToAmount(totalSettledCents) ?? 0,
      outstanding: centsToAmount(outstandingCents),
      mismatchAmount: centsToAmount(mismatchCents) ?? 0,
      status,
      voucherRefs: vouchers.map((v) => v.ledgerRowId),
    });
  }
  return summaries;
}
