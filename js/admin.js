/**
 * Orbital Trading - Master Admin Portal Logic
 * Payouts, Returns, and 24h Daily Settlements
 */

document.addEventListener("DOMContentLoaded", () => {
  let isAdminAuthenticated = false;
  let activePayoutUser = null;

  // Mock initial state / persistent storage
  let adminUsers = JSON.parse(localStorage.getItem("orbital_admin_users") || "null") || [
    {
      id: 1,
      email: "trade09siam@gmail.com",
      bep20_address: "0x66A06fA03BE98383fe4F73a5f1783332CAC0F5A0",
      balance_usdt: 13.13,
      auto_compound: true,
      account_status: "ACTIVE"
    },
    {
      id: 2,
      email: "trader_alpha@orbital.trading",
      bep20_address: "0x12aB34cD56eF78901234567890abcdef12345678",
      balance_usdt: 250.00,
      auto_compound: true,
      account_status: "ACTIVE"
    }
  ];

  let adminDeposits = JSON.parse(localStorage.getItem("orbital_admin_deposits") || "null") || [
    {
      tx_hash: "0x3f7a1b8c9d0e2f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a",
      email: "trade09siam@gmail.com",
      amount_usdt: 13.13,
      status: "VERIFIED_ON_CHAIN",
      created_at: "2026-08-25 18:30:00"
    }
  ];

  // Elements
  const loginSection = document.getElementById("admin-login-section");
  const dashboardSection = document.getElementById("admin-dashboard-section");
  const loginForm = document.getElementById("admin-login-form");
  const btnLogout = document.getElementById("btn-admin-logout");

  const admTotalUsers = document.getElementById("adm-total-users");
  const admTotalDeposited = document.getElementById("adm-total-deposited");
  const admActiveCapital = document.getElementById("adm-active-capital");
  const admUsersTbody = document.getElementById("adm-users-tbody");
  const admDepositsTbody = document.getElementById("adm-deposits-tbody");

  const adminSettleForm = document.getElementById("admin-settle-form");
  const modalPayout = document.getElementById("modal-payout");
  const payoutUserEmail = document.getElementById("payout-user-email");
  const payoutUserBep20 = document.getElementById("payout-user-bep20");
  const payoutAmount = document.getElementById("payout-amount");
  const payoutTxHash = document.getElementById("payout-tx-hash");
  const btnConfirmPayout = document.getElementById("btn-confirm-payout");
  const btnCopyPayoutBep20 = document.getElementById("btn-copy-payout-bep20");

  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function openModal(modal) {
    if (modal) modal.classList.add("active");
  }

  function closeModal(modal) {
    if (modal) modal.classList.remove("active");
  }

  document.querySelectorAll(".modal-close").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const modalId = e.target.getAttribute("data-close");
      closeModal(document.getElementById(modalId));
    });
  });

  // Admin Login
  if (loginForm) {
    loginForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const passkey = document.getElementById("admin-passkey").value.trim();
      if (passkey === "01644" || passkey.includes("01644")) {
        isAdminAuthenticated = true;
        sessionStorage.setItem("orbital_admin_auth", "true");
        loginSection.style.display = "none";
        dashboardSection.style.display = "block";
        btnLogout.style.display = "inline-block";
        showToast("🔓 Master Admin unlocked successfully.", "success");
        renderAdminDashboard();
      } else {
        showToast("❌ Invalid master passkey. Access denied.", "error");
      }
    });
  }

  // Admin Logout
  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      isAdminAuthenticated = false;
      sessionStorage.removeItem("orbital_admin_auth");
      loginSection.style.display = "block";
      dashboardSection.style.display = "none";
      btnLogout.style.display = "none";
      showToast("Admin session locked.", "info");
    });
  }

  // Copy Payout BEP20 Address
  if (btnCopyPayoutBep20) {
    btnCopyPayoutBep20.addEventListener("click", () => {
      if (payoutUserBep20) {
        navigator.clipboard.writeText(payoutUserBep20.value).then(() => {
          showToast("📋 User BEP-20 payout address copied!", "success");
        });
      }
    });
  }

  // Render Admin Tables & Summary
  function renderAdminDashboard() {
    // 1. Stats
    const totalUsers = adminUsers.length;
    const totalCapital = adminUsers.reduce((sum, u) => sum + Number(u.balance_usdt || 0), 0);
    const totalDeposited = adminDeposits.reduce((sum, d) => sum + Number(d.amount_usdt || 0), 0);

    admTotalUsers.textContent = totalUsers;
    admTotalDeposited.textContent = `$${totalDeposited.toFixed(2)}`;
    admActiveCapital.textContent = `$${totalCapital.toFixed(2)}`;

    // 2. Users Table
    admUsersTbody.innerHTML = adminUsers.map(u => {
      const bal = Number(u.balance_usdt || 0);
      return `
        <tr>
          <td><span class="mono">#${u.id}</span></td>
          <td><strong>${u.email}</strong></td>
          <td><code style="color: var(--accent-cyan); font-size: 0.8rem;">${u.bep20_address}</code></td>
          <td class="mono" style="font-weight: 700; color: #fff;">$${bal.toFixed(2)} USDT</td>
          <td><span class="status-badge" style="font-size: 0.75rem;">${u.auto_compound ? 'AUTO-COMPOUND 🟢' : 'PAYOUT 🟡'}</span></td>
          <td><span class="status-badge active" style="font-size: 0.75rem;">${u.account_status}</span></td>
          <td>
            <button class="payout-btn" onclick="window.openPayoutModal(${u.id})">
              💸 Return / Payout
            </button>
          </td>
        </tr>
      `;
    }).join("");

    // 3. Deposits Table
    admDepositsTbody.innerHTML = adminDeposits.map(d => {
      const shortTx = `${d.tx_hash.substring(0, 10)}...${d.tx_hash.substring(58)}`;
      return `
        <tr>
          <td>
            <a href="https://bscscan.com/tx/${d.tx_hash}" target="_blank" style="color: var(--accent-cyan); text-decoration: none; font-family: monospace;">
              ${shortTx} ↗
            </a>
          </td>
          <td>${d.email}</td>
          <td class="mono" style="font-weight: 700; color: var(--accent-emerald);">+$${Number(d.amount_usdt).toFixed(2)}</td>
          <td><span class="status-badge active" style="font-size: 0.75rem;">VERIFIED ON-CHAIN 🟢</span></td>
          <td style="color: var(--text-muted); font-size: 0.85rem;">${d.created_at}</td>
        </tr>
      `;
    }).join("");
  }

  // Open Payout Modal
  window.openPayoutModal = function(userId) {
    const user = adminUsers.find(u => u.id === userId);
    if (!user) return;
    activePayoutUser = user;

    payoutUserEmail.value = user.email;
    payoutUserBep20.value = user.bep20_address;
    payoutAmount.value = user.balance_usdt;
    payoutTxHash.value = "";

    openModal(modalPayout);
  };

  // Confirm Payout & Deduct / Return Capital
  if (btnConfirmPayout) {
    btnConfirmPayout.addEventListener("click", () => {
      if (!activePayoutUser) return;
      const returnAmt = parseFloat(payoutAmount.value);
      const txHash = payoutTxHash.value.trim();

      if (isNaN(returnAmt) || returnAmt <= 0) {
        showToast("Please enter a valid return amount.", "error");
        return;
      }

      if (returnAmt > activePayoutUser.balance_usdt) {
        showToast("Return amount exceeds user's active vault balance.", "error");
        return;
      }

      activePayoutUser.balance_usdt = Math.max(0, activePayoutUser.balance_usdt - returnAmt);
      localStorage.setItem("orbital_admin_users", JSON.stringify(adminUsers));

      closeModal(modalPayout);
      showToast(`✅ Successfully processed return of $${returnAmt.toFixed(2)} USDT to ${activePayoutUser.bep20_address}!`, "success");
      renderAdminDashboard();
    });
  }

  // Execute 24h Settlement
  if (adminSettleForm) {
    adminSettleForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const roiInput = document.getElementById("input-daily-roi");
      const roiPct = parseFloat(roiInput.value);

      if (isNaN(roiPct)) {
        showToast("Please enter a valid daily ROI %.", "error");
        return;
      }

      // Apply settlement logic across users:
      // WIN (>0): 60% user, 40% platform
      // LOSS (<=0): 100% loss to user, 0% platform fee
      adminUsers.forEach(u => {
        const bal = Number(u.balance_usdt || 0);
        if (bal > 0) {
          if (roiPct > 0) {
            const userNetPct = roiPct * 0.60;
            const netGain = bal * (userNetPct / 100.0);
            u.balance_usdt = Math.round((bal + netGain) * 100) / 100;
          } else {
            const netLoss = bal * (roiPct / 100.0);
            u.balance_usdt = Math.max(0, Math.round((bal + netLoss) * 100) / 100);
          }
        }
      });

      localStorage.setItem("orbital_admin_users", JSON.stringify(adminUsers));
      roiInput.value = "";
      showToast(`🎉 24h Settlement Executed at ${roiPct >= 0 ? '+' : ''}${roiPct.toFixed(2)}% ROI across all active users!`, "success");
      renderAdminDashboard();
    });
  }

  // Check persistent session
  if (sessionStorage.getItem("orbital_admin_auth") === "true") {
    isAdminAuthenticated = true;
    loginSection.style.display = "none";
    dashboardSection.style.display = "block";
    btnLogout.style.display = "inline-block";
    renderAdminDashboard();
  }
});
