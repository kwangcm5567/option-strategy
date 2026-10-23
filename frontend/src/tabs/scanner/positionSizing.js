/** @param {number} accountSize @param {number|null} maxLoss @param {number|null} capitalRequired */
export function riskLimitedContracts(accountSize, maxLoss, capitalRequired) {
  if (!Number.isFinite(accountSize) || accountSize <= 0 || !Number.isFinite(maxLoss) || maxLoss <= 0) return 0;
  const riskLimit = Math.floor(accountSize * 0.02 / maxLoss);
  const cashLimit = Number.isFinite(capitalRequired) && capitalRequired > 0
    ? Math.floor(accountSize / capitalRequired) : 0;
  return Math.max(0, Math.min(riskLimit, cashLimit));
}
