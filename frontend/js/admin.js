/**
 * ApexTrade AI - Master Admin Portal Controller
 * Restricted strictly to platform administrator.
 * Aggregates all user confirmations, withdrawal payouts, and daily pool settlements.
 */

document.addEventListener("DOMContentLoaded", () => {

  const adminGateSection = document.getElementById("admin-gate-section");
  const adminMainContent = document.getElementById("admin-main-content");
  const formAdminAuth = document.getElementById("form-admin-auth");
  const inputAdminPasskey = document.getElementById("input-admin-passkey");
  const adminAuthAlert = document.getElementById("admin-auth-alert");
  const authStatusBadge = document.getElementById("auth-status-badge");
  const btnAdminLogout = document.getElementById("btn-admin-logout");

  const adminWithdrawalsTbody = document.getElementById("admin-withdrawals-tbody");
  const adminPendingBadge = document.getElementById("admin-pending-badge");
  const adminHeaderPendingCount = document.getElementById("admin-header-pending-count");
  const btnRefreshAdminWithdrawals = document.getElementById("btn-refresh-admin-withdrawals");

  const adminDepositsTbody = document.getElementById("admin-deposits-tbody");
  const btnRefreshAdminDeposits = document.getElementById("btn-refresh-admin-deposits");

  const adminSettleRoi = document.getElementById("admin-settle-roi");
  const btnAdminSettle = document.getElementById("btn-admin-settle");
  const adminSettleAlert = document.getElementById("admin-settle-alert");

  const adminBatchPool = document.getElementById("admin-batch-pool");
  const adminBatchCount = document.getElementById("admin-batch-count");
  const btnAdminSweep = document.getElementById("btn-admin-sweep");
  const adminSweepAlert = document.getElementById("admin-sweep-alert");

  // Check existing session
  let adminPasskey = sessionStorage.getItem("apextrade_admin_passkey") || "";
  const savedAdminAuth = sessionStorage.getItem("apextrade_admin_authenticated");
  if (savedAdminAuth === "true" && adminPasskey) {
    unlockAdminConsole();
  }

  function getAdminHeaders() {
    return {
      "Content-Type": "application/json",
      "X-Admin-Passkey": adminPasskey || sessionStorage.getItem("apextrade_admin_passkey") || ""
    };
  }

  formAdminAuth.addEventListener("submit", async (e) => {
    e.preventDefault();
    const passkey = inputAdminPasskey.value.trim();

    try {
      const res = await fetch("/api/admin/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Admin-Passkey": passkey },
        body: JSON.stringify({ passcode: passkey })
      });
      const data = await res.json();

      if (data.success) {
        adminPasskey = passkey;
        sessionStorage.setItem("apextrade_admin_passkey", passkey);
        sessionStorage.setItem("apextrade_admin_authenticated", "true");
        unlockAdminConsole();
      } else {
        showAuthAlert(data.message || "Invalid passkey. Access denied.");
      }
    } catch (err) {
      showAuthAlert("Network error validating admin credentials.");
    }
  });

  if (btnAdminLogout) {
    btnAdminLogout.addEventListener("click", () => {
      adminPasskey = "";
      sessionStorage.removeItem("apextrade_admin_passkey");
      sessionStorage.removeItem("apextrade_admin_authenticated");
      adminGateSection.style.display = "block";
      adminMainContent.style.display = "none";
      authStatusBadge.className = "admin-badge";
      authStatusBadge.textContent = "🔒 ACCESS RESTRICTED";
      btnAdminLogout.style.display = "none";
    });
  }

  function unlockAdminConsole() {
    adminGateSection.style.display = "none";
    adminMainContent.style.display = "block";
    authStatusBadge.className = "status-badge active";
    authStatusBadge.textContent = "🛡️ ADMIN AUTHORIZED";
    if (btnAdminLogout) btnAdminLogout.style.display = "inline-flex";

    loadAllPendingWithdrawals();
    loadAllPlatformDeposits();
  }

  function showAuthAlert(msg) {
    adminAuthAlert.style.display = "block";
    adminAuthAlert.className = "form-alert error";
    adminAuthAlert.textContent = msg;
  }

  // ==========================================
  // 1. ALL USERS' PENDING WITHDRAWALS
  // ==========================================
  async function loadAllPendingWithdrawals() {
    if (!adminWithdrawalsTbody) return;
    try {
      const res = await fetch("/api/admin/withdrawals", { headers: getAdminHeaders() });
      const data = await res.json();

      if (data.success && data.pending_withdrawals) {
        const list = data.pending_withdrawals;
        if (adminPendingBadge) adminPendingBadge.textContent = `${list.length} PENDING`;
        if (adminHeaderPendingCount) adminHeaderPendingCount.innerHTML = `${list.length} <span style="font-size: 1rem; color: var(--text-secondary);">Requests</span>`;

        if (list.length === 0) {
          adminWithdrawalsTbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                ✅ No pending withdrawal requests. All requests from all users have been processed.
              </td>
            </tr>
          `;
          return;
        }

        adminWithdrawalsTbody.innerHTML = list.map(w => {
          const userBep20 = w.destination_bep20 || '0x...';
          const destShort = `${userBep20.substring(0, 10)}...${userBep20.substring(userBep20.length - 8)}`;
          return `
            <tr>
              <td class="mono" style="font-weight: 700;">#${w.id}</td>
              <td style="font-weight: 600;">${w.email || 'Trader'}</td>
              <td class="mono" style="font-weight: 700; color: #f87171; font-size: 1rem;">-$${Number(w.amount_usdt).toFixed(2)} USDT</td>
              <td class="mono" title="${userBep20}" style="color: var(--accent-cyan);">${destShort}</td>
              <td style="font-size: 0.85rem;">${w.created_at || 'Just now'}</td>
              <td>
                <div style="display: flex; gap: 0.5rem;">
                  <button class="btn btn-primary btn-sm" onclick="window.adminApprovePayout(${w.id}, ${w.amount_usdt}, '${userBep20}')" style="background: linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan)); color:#0b1120; font-weight:800; padding: 0.35rem 0.85rem; font-size: 0.8rem; cursor: pointer;">
                    ✅ Confirm & Dispatch Payout
                  </button>
                  <button class="btn btn-secondary btn-sm" onclick="window.adminRejectPayout(${w.id})" style="border-color: rgba(239, 68, 68, 0.5); color:#f87171; padding: 0.35rem 0.75rem; font-size: 0.8rem; cursor: pointer;">
                    ❌ Reject & Refund
                  </button>
                </div>
              </td>
            </tr>
          `;
        }).join("");
      }
    } catch (e) {
      console.error("Failed to load pending withdrawals:", e);
    }
  }

  window.adminApprovePayout = async function(id, amount, dest) {
    if (!confirm(`CONFIRM PAYOUT AUTHORIZATION:\n\nApprove Withdrawal #${id} of $${Number(amount).toFixed(2)} USDT?\n\nFunds will be marked DISPATCHED from Master System Address (0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0) to user BEP-20 address (${dest}).`)) {
      return;
    }

    try {
      const res = await fetch("/api/admin/withdrawals/approve", {
        method: "POST",
        headers: getAdminHeaders(),
        body: JSON.stringify({ withdrawal_id: id })
      });
      const data = await res.json();
      if (data.success) {
        alert(`🎉 ${data.message}`);
        await loadAllPendingWithdrawals();
      } else {
        alert(`Error: ${data.message}`);
      }
    } catch (e) {
      alert("Network error processing approval.");
    }
  };

  window.adminRejectPayout = async function(id) {
    const reason = prompt("Enter reason for rejecting this withdrawal (funds will be refunded to user's trading capital):", "Admin rejected");
    if (reason === null) return;

    try {
      const res = await fetch("/api/admin/withdrawals/reject", {
        method: "POST",
        headers: getAdminHeaders(),
        body: JSON.stringify({ withdrawal_id: id, reason: reason })
      });
      const data = await res.json();
      if (data.success) {
        alert(`Withdrawal #${id} rejected and funds refunded to user.`);
        await loadAllPendingWithdrawals();
      } else {
        alert(`Error: ${data.message}`);
      }
    } catch (e) {
      alert("Network error rejecting withdrawal.");
    }
  };

  if (btnRefreshAdminWithdrawals) btnRefreshAdminWithdrawals.addEventListener("click", loadAllPendingWithdrawals);

  // ==========================================
  // 2. ALL USERS' CONFIRMED DEPOSITS LEDGER
  // ==========================================
  async function loadAllPlatformDeposits() {
    if (!adminDepositsTbody) return;
    try {
      const res = await fetch("/api/admin/deposits", { headers: getAdminHeaders() });
      const data = await res.json();

      if (data.success && data.deposits) {
        if (data.deposits.length === 0) {
          adminDepositsTbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                No deposits recorded across the platform yet.
              </td>
            </tr>
          `;
          return;
        }

        adminDepositsTbody.innerHTML = data.deposits.map(d => {
          const senderShort = d.from_address ? `${d.from_address.substring(0, 8)}...${d.from_address.substring(d.from_address.length - 6)}` : '0x...';
          const txShort = d.tx_hash ? `${d.tx_hash.substring(0, 10)}...${d.tx_hash.substring(d.tx_hash.length - 8)}` : '0x...';
          return `
            <tr>
              <td>${d.created_at || 'Recently'}</td>
              <td style="font-weight: 600;">${d.email || 'Trader'}</td>
              <td class="mono" style="font-weight: 700; color: var(--accent-emerald);">+$${Number(d.amount_usdt).toFixed(2)} USDT</td>
              <td class="mono" title="${d.from_address}">${senderShort}</td>
              <td class="mono" style="font-size: 0.8rem; color: var(--accent-cyan);" title="${d.tx_hash}">${txShort}</td>
              <td><span class="status-badge active">CONFIRMED BSC</span></td>
            </tr>
          `;
        }).join("");
      }
    } catch (e) {
      console.error("Failed to load platform deposits:", e);
    }
  }

  if (btnRefreshAdminDeposits) btnRefreshAdminDeposits.addEventListener("click", loadAllPlatformDeposits);

});
