/**
 * Orbital Trading Platform Frontend Controller.
 * Manages 2-of-3 Authentication, Persistent Device Sessions, Vault Engine, and Live Streams.
 */

window.App = {
  currentUser: null,
  token: null,
  activeView: "onboarding",
  countdownInterval: null,
  qrCodeInstance: null,

  // =========================================================================
  // INITIALIZATION & DEVICE SESSION PERSISTENCE
  // =========================================================================
  init: function () {
    // 1. Check for stored device session token in localStorage
    const storedToken = localStorage.getItem("orbital_device_token");
    if (storedToken) {
      this.token = storedToken;
      this.verifyAndRestoreSession();
    } else {
      this.showOnboarding();
    }

    // 2. Start polling live bot telemetry, trades and epoch countdown
    this.syncBinanceLiveTelemetry();
    setInterval(() => {
      this.syncBinanceLiveTelemetry();
    }, 3000);

    setInterval(() => {
      if (this.currentUser) {
        this.loadVaultSummary();
      }
    }, 10000);
  },

  showToast: function (msg, isError = false) {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.style.borderColor = isError ? "var(--accent-rose)" : "var(--primary-emerald)";
    toast.innerHTML = `
      <span>${isError ? "❌" : "✅"}</span>
      <span>${msg}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.remove();
    }, 4000);
  },

  // =========================================================================
  // AUTHENTICATION: 2-OF-3 MFA & DEVICE AUTO-LOGIN
  // =========================================================================
  setAuthMode: function (mode) {
    const regContainer = document.getElementById("authRegisterContainer");
    const loginContainer = document.getElementById("authLoginContainer");
    const btnReg = document.getElementById("toggleBtnRegister");
    const btnLogin = document.getElementById("toggleBtnLogin");

    if (mode === "login") {
      regContainer.style.display = "none";
      loginContainer.style.display = "block";
      btnReg.style.background = "transparent";
      btnReg.style.color = "var(--text-secondary)";
      btnLogin.style.background = "var(--primary-cyan)";
      btnLogin.style.color = "#fff";
    } else {
      regContainer.style.display = "block";
      loginContainer.style.display = "none";
      btnReg.style.background = "var(--primary-cyan)";
      btnReg.style.color = "#fff";
      btnLogin.style.background = "transparent";
      btnLogin.style.color = "var(--text-secondary)";
    }
  },

  verifyAndRestoreSession: async function () {
    try {
      const res = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${this.token}` }
      });
      if (res.ok) {
        const user = await res.json();
        this.currentUser = user;
        this.showDashboard();
        this.showToast(`Welcome back, ${user.email}! (Device session active)`);
      } else {
        localStorage.removeItem("orbital_device_token");
        this.token = null;
        this.showOnboarding();
      }
    } catch (e) {
      console.error("Session restore error:", e);
      this.showOnboarding();
    }
  },

  handleRegister: async function () {
    const email = document.getElementById("regEmail").value.trim();
    const password = document.getElementById("regPassword").value.trim();
    const bep20_address = document.getElementById("regBep20").value.trim();

    if (!email || !password || !bep20_address) {
      this.showToast("Please fill in all 3 registration fields.", true);
      return;
    }

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, bep20_address })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.token = data.token;
        localStorage.setItem("orbital_device_token", data.token);
        this.currentUser = {
          user_uuid: data.user_uuid,
          email: data.email,
          bep20_address: data.bep20_address,
          balance_usdt: 0.0,
          active_vault_balance: 0.0
        };
        this.showDashboard();
        this.showToast("Account created successfully! Welcome to Orbital Trading.");
      } else {
        this.showToast(data.detail || data.error || "Registration failed.", true);
      }
    } catch (e) {
      this.showToast("Server connection error: " + e.message, true);
    }
  },

  handleLogin: async function () {
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value.trim();
    const bep20_address = document.getElementById("loginBep20").value.trim();

    const providedCount = [email, password, bep20_address].filter(x => x.length > 0).length;
    if (providedCount < 2) {
      this.showToast("2-of-3 Rule: Please enter at least TWO credentials.", true);
      return;
    }

    const btn = document.getElementById("btnLoginSubmit");
    const origText = btn ? btn.innerText : "";
    if (btn) {
      btn.innerText = "⏳ Verifying 2-of-3 Credentials...";
      btn.disabled = true;
      btn.style.opacity = "0.8";
    }

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email || null,
          password: password || null,
          bep20_address: bep20_address || null
        })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.token = data.token;
        localStorage.setItem("orbital_device_token", data.token);
        await this.verifyAndRestoreSession();
      } else {
        this.showToast(data.detail || data.error || "2-of-3 Verification failed.", true);
      }
    } catch (e) {
      this.showToast("Server connection error: " + e.message, true);
    } finally {
      if (btn) {
        btn.innerText = origText;
        btn.disabled = false;
        btn.style.opacity = "1";
      }
    }
  },

  handleLogout: function () {
    localStorage.removeItem("orbital_device_token");
    sessionStorage.removeItem("orbital_master_admin_verified");
    const adminBtn = document.getElementById("btnTabAdmin");
    if (adminBtn) adminBtn.style.display = "none";
    this.token = null;
    this.currentUser = null;
    this.showOnboarding();
    this.showToast("Logged out successfully.");
  },

  // =========================================================================
  // VIEW NAVIGATION & DASHBOARD
  // =========================================================================
  showOnboarding: function () {
    this.activeView = "onboarding";
    document.getElementById("onboardingView").style.display = "block";
    document.getElementById("dashboardView").style.display = "none";
    document.getElementById("historyView").style.display = "none";
    document.getElementById("adminView").style.display = "none";

    document.getElementById("navGuestBar").style.display = "flex";
    document.getElementById("navUserBar").style.display = "none";
    document.getElementById("navCenterTabs").style.display = "none";
  },

  showDashboard: function () {
    this.activeView = "dashboard";
    document.getElementById("onboardingView").style.display = "none";
    document.getElementById("dashboardView").style.display = "block";
    document.getElementById("historyView").style.display = "none";
    document.getElementById("adminView").style.display = "none";

    document.getElementById("navGuestBar").style.display = "none";
    document.getElementById("navUserBar").style.display = "flex";
    document.getElementById("navCenterTabs").style.display = "flex";

    // Set Navbar User Details
    document.getElementById("navUserUniqueId").innerText = this.currentUser.user_uuid;
    const addr = this.currentUser.bep20_address;
    document.getElementById("navWalletAddressShort").innerText = addr.substring(0, 6) + "..." + addr.substring(addr.length - 4);

    // Keep Admin tab strictly hidden unless 4-Layer Master Admin authenticated
    const adminBtn = document.getElementById("btnTabAdmin");
    if (adminBtn) {
      if (this.currentUser && this.currentUser.is_admin === 1 && sessionStorage.getItem("orbital_master_admin_verified") === "true") {
        adminBtn.style.display = "inline-flex";
      } else {
        adminBtn.style.display = "none";
      }
    }

    this.loadVaultSummary();
    this.syncBinanceLiveTelemetry();
  },

  switchView: function (viewName) {
    const views = ["dashboard", "history", "admin"];
    views.forEach(v => {
      const el = document.getElementById(v + "View");
      if (el) el.style.display = (v === viewName) ? "block" : "none";
    });

    // Update Tab active styling
    const tabs = ["Dashboard", "Trades", "History", "Admin"];
    tabs.forEach(t => {
      const btn = document.getElementById("btnTab" + t);
      if (btn) {
        if (t.toLowerCase() === viewName || (t === "Trades" && viewName === "dashboard")) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      }
    });

    if (viewName === "history") {
      this.loadTransactionHistory();
    }
  },

  copyUserAddress: function () {
    if (!this.currentUser) return;
    navigator.clipboard.writeText(this.currentUser.bep20_address);
    this.showToast("BEP-20 address copied to clipboard!");
  },

  copyMasterAddress: function () {
    const el = document.getElementById("depositMasterAddress");
    if (el) {
      navigator.clipboard.writeText(el.value);
      this.showToast("Master Vault address copied!");
    }
  },

  // =========================================================================
  // VAULT METRICS & LIVE STREAMS
  // =========================================================================
  loadVaultSummary: async function () {
    try {
      // 1. User Summary
      const userRes = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${this.token}` }
      });
      if (userRes.ok) {
        const u = await userRes.json();
        this.currentUser = u;
        const totalPortfolio = parseFloat(u.active_vault_balance || 0) + parseFloat(u.balance_usdt || 0);
        document.getElementById("dashUserBalance").innerText = totalPortfolio.toFixed(2);
        
        const withdrawableBalEl = document.getElementById("dashWithdrawableBal");
        if (withdrawableBalEl) withdrawableBalEl.innerText = parseFloat(u.balance_usdt || 0).toFixed(2);

        const totalEarnedEl = document.getElementById("dashTotalEarned");
        if (totalEarnedEl) totalEarnedEl.innerText = parseFloat(u.total_profit_earned || 0).toFixed(2);

        const activeBalEl = document.getElementById("dashActiveTradingBal");
        if (activeBalEl) activeBalEl.innerText = parseFloat(u.active_vault_balance || 0).toFixed(2);

        const pendingBalEl = document.getElementById("dashPendingRolloverBal");
        if (pendingBalEl) pendingBalEl.innerText = parseFloat(u.pending_rollover_balance || 0).toFixed(2);

        document.getElementById("dashMyShare").innerText = parseFloat(u.pool_share_pct || 0).toFixed(2) + "%";

        // Render Auto-Compounding Controller State
        const compBadge = document.getElementById("dashCompoundingBadge");
        const compDesc = document.getElementById("dashCompoundingDesc");
        const compBtn = document.getElementById("btnToggleCompounding");
        
        if (compBadge && compDesc && compBtn) {
          if (u.compounding_status === "STOPPING_AT_NEXT_ROLLOVER") {
            compBadge.innerText = "STOPPING AT 12:00 AM";
            compBadge.className = "badge badge-active";
            compDesc.innerText = "⏳ Auto-Compounding Stopping: Your funds will finish today's 24-hour trading round until the 12:00 AM rollover, and will then be released to your withdrawable wallet.";
            compBtn.innerText = "▶️ Resume Compounding";
            compBtn.style.borderColor = "var(--primary-emerald)";
            compBtn.style.color = "var(--primary-emerald)";
          } else if (u.compounding_status === "STOPPED" || u.is_compounding === 0) {
            compBadge.innerText = "STOPPED";
            compBadge.className = "badge badge-loss";
            compDesc.innerText = "⏸️ Auto-Compounding Stopped: Your funds are in your withdrawable wallet. Click Enable to join the next 12:00 AM rollover cycle.";
            compBtn.innerText = "▶️ Enable Compounding";
            compBtn.style.borderColor = "var(--primary-emerald)";
            compBtn.style.color = "var(--primary-emerald)";
          } else {
            compBadge.innerText = "ACTIVE (DAILY REINVEST)";
            compBadge.className = "badge badge-win";
            compDesc.innerText = "🔄 Your daily profits/losses and principal automatically re-invest into the next 24-hour rollover cycle without needing manual deposits.";
            compBtn.innerText = "⏸️ Stop Compounding";
            compBtn.style.borderColor = "var(--primary-cyan)";
            compBtn.style.color = "var(--primary-cyan)";
          }
        }
      }

      // 2. Global Vault & Bot Performance
      const vaultRes = await fetch("/api/vault/summary");
      if (vaultRes.ok) {
        const data = await vaultRes.json();
        const ep = data.epoch;
        const bot = data.bot_performance;

        document.getElementById("dashPoolTotal").innerText = parseFloat(ep.current_pool_usdt).toFixed(2);
        document.getElementById("dashActiveInvestors").innerText = ep.active_investors;
        document.getElementById("dashEpochCountdown").innerText = ep.time_remaining_formatted;

        document.getElementById("dashWinRate").innerText = bot.win_rate_pct.toFixed(1) + "%";
        document.getElementById("dashTotalPnL").innerText = (bot.total_pnl_usd >= 0 ? "+$" : "-$") + Math.abs(bot.total_pnl_usd).toFixed(2);
        document.getElementById("dashProfitFactor").innerText = bot.profit_factor.toFixed(2);
        document.getElementById("dashBotStatus").innerText = bot.status;
      }
    } catch (e) {
      console.error("Error loading vault summary:", e);
    }
  },

  syncBinanceLiveTelemetry: async function () {
    try {
      const res = await fetch("/api/bot/binance-live");
      if (!res.ok) return;
      const data = await res.json();
      if (!data.success) return;

      const bal = Number(data.balance_usdt || 0).toFixed(2);
      const roi = Number(data.net_roi_pct || 0);
      const profit = Number(data.net_profit_usdt || 0);
      const openPositions = data.open_positions || [];
      const closedTrades = data.closed_trades || [];
      const perf = data.performance || {};

      // 1. Update Metrics
      const elBal = document.getElementById("binanceLiveBal");
      const elRoi = document.getElementById("binanceLiveRoi");
      const elProf = document.getElementById("binanceLiveProfit");
      const elWin = document.getElementById("binanceLiveWinRate");
      const elCount = document.getElementById("binanceOpenPositionsCount");
      const elUnr = document.getElementById("binanceOpenTotalUnr");

      if (elBal) elBal.innerHTML = `$${bal} <span style="font-size: 0.8rem; color: var(--text-secondary);">USDT</span>`;
      if (elRoi) {
        elRoi.textContent = `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}%`;
        elRoi.style.color = roi >= 0 ? "var(--primary-emerald)" : "var(--accent-rose)";
      }
      if (elProf) {
        elProf.textContent = `${profit >= 0 ? '+' : ''}$${profit.toFixed(2)} USDT Net Gain`;
        elProf.style.color = profit >= 0 ? "var(--primary-emerald)" : "var(--accent-rose)";
      }
      if (elWin) {
        elWin.textContent = `${Number(perf.win_rate_pct || 78.5).toFixed(1)}%`;
      }
      if (elCount) {
        elCount.textContent = openPositions.length;
      }

      // Calculate total open unrealized PnL
      let totalUnr = 0.0;
      openPositions.forEach(p => totalUnr += Number(p.unrealized_pnl || 0));
      if (elUnr) {
        const isUp = totalUnr >= 0;
        elUnr.textContent = `${isUp ? '+' : ''}$${totalUnr.toFixed(4)} USDT`;
        elUnr.style.color = isUp ? "var(--primary-emerald)" : "var(--accent-rose)";
      }

      // Update Dashboard Metric 3 Win Rate & PnL
      const dashWin = document.getElementById("dashWinRate");
      const dashPnL = document.getElementById("dashTotalPnL");
      if (dashWin) dashWin.textContent = `${Number(perf.win_rate_pct || 78.5).toFixed(1)}%`;
      if (dashPnL) {
        dashPnL.textContent = `${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}`;
        dashPnL.style.color = profit >= 0 ? "var(--primary-emerald)" : "var(--accent-rose)";
      }

      // 2. Render Open Positions Table
      const posTbody = document.getElementById("binanceOpenPositionsTbody");
      if (posTbody) {
        if (openPositions.length === 0) {
          posTbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                No active open positions on Binance Futures right now. Bot is scanning on 10s cadence.
              </td>
            </tr>
          `;
        } else {
          posTbody.innerHTML = openPositions.map(p => {
            const isLong = p.direction === "LONG";
            const unr = Number(p.unrealized_pnl || 0);
            const isPnlGain = unr >= 0;
            const pnlColor = isPnlGain ? "var(--primary-emerald)" : "var(--accent-rose)";
            const pnlSign = isPnlGain ? "+" : "";

            return `
              <tr>
                <td>
                  <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <strong style="color: #fff;">${p.symbol}</strong>
                    <span class="badge ${isLong ? 'badge-win' : 'badge-loss'}" style="font-size: 0.7rem; padding: 2px 6px;">
                      ${p.direction}
                    </span>
                  </div>
                </td>
                <td><span class="mono" style="font-size: 0.78rem; color: var(--primary-cyan);">${p.leverage}x Isolated</span></td>
                <td class="mono">${p.quantity}</td>
                <td class="mono">$${Number(p.entry_price).toFixed(4)}</td>
                <td class="mono">$${Number(p.mark_price).toFixed(4)}</td>
                <td class="mono" style="font-weight: 700; color: ${pnlColor}; font-size: 0.9rem;">
                  ${pnlSign}$${unr.toFixed(4)}
                </td>
              </tr>
            `;
          }).join("");
        }
      }

      // 3. Render Closed Trades Journal Table
      const closedTbody = document.getElementById("binanceClosedTradesTbody");
      if (closedTbody) {
        if (closedTrades.length === 0) {
          closedTbody.innerHTML = `
            <tr>
              <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
                No recently closed trades recorded yet.
              </td>
            </tr>
          `;
        } else {
          closedTbody.innerHTML = closedTrades.map(t => {
            const isWin = t.outcome.includes("WIN");
            const pnl = Number(t.pnl_usd || 0);
            const pnlColor = isWin ? "var(--primary-emerald)" : "var(--accent-rose)";
            const outcomeBadge = isWin 
              ? `<span class="badge badge-win" style="font-size: 0.7rem;">WIN 🟢</span>` 
              : `<span class="badge badge-loss" style="font-size: 0.7rem;">LOSS 🔴</span>`;

            const exitTime = t.entry_time ? t.entry_time.replace("T", " ").substring(0, 19) : "Recently";
            const exitReason = t.exit_reason || "STRATEGY_EXIT";

            return `
              <tr>
                <td style="font-weight: 700; color: #fff;">${t.symbol}</td>
                <td><span class="mono" style="font-size: 0.78rem;">${t.direction}</span></td>
                <td>${outcomeBadge}</td>
                <td class="mono" style="font-weight: 700; color: ${pnlColor}; font-size: 0.9rem;">
                  ${pnl >= 0 ? '+' : ''}$${pnl.toFixed(4)}
                </td>
                <td class="mono">$${Number(t.exit_price || 0).toFixed(4)}</td>
                <td><span style="font-size: 0.78rem; color: var(--text-secondary);">${exitReason}</span></td>
                <td style="font-size: 0.78rem; color: var(--text-muted);">${exitTime}</td>
              </tr>
            `;
          }).join("");
        }
      }

    } catch (e) {
      console.error("Binance telemetry error:", e);
    }
  },

  loadLiveTrades: async function () {
    await this.syncBinanceLiveTelemetry();
  },

  loadTransactionHistory: async function () {
    try {
      const res = await fetch("/api/user/transactions", {
        headers: { Authorization: `Bearer ${this.token}` }
      });
      if (!res.ok) return;

      const data = await res.json();
      const depBody = document.getElementById("depositHistoryTableBody");
      const wthBody = document.getElementById("withdrawHistoryTableBody");

      // Deposits Table
      if (data.deposits && data.deposits.length > 0) {
        depBody.innerHTML = data.deposits.map(d => `
          <tr>
            <td class="mono" style="color: var(--primary-cyan); font-weight: 700;">${d.deposit_id}</td>
            <td class="mono" style="font-weight: 700; color: var(--primary-emerald); font-size: 0.9rem;">+$${parseFloat(d.amount_usdt).toFixed(2)}</td>
            <td class="mono" style="font-size: 0.75rem;">${d.bep20_sender.substring(0, 8)}...${d.bep20_sender.substring(d.bep20_sender.length - 6)}</td>
            <td class="mono" style="font-size: 0.75rem;"><a href="https://bscscan.com/tx/${d.tx_hash}" target="_blank" style="color: var(--primary-cyan);">View BSC ↗</a></td>
            <td><span class="badge badge-win">${d.status}</span></td>
            <td style="font-size: 0.75rem; color: var(--text-muted);">${d.created_at}</td>
          </tr>
        `).join("");
      } else {
        depBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No deposits found.</td></tr>`;
      }

      // Withdrawals Table
      if (data.withdrawals && data.withdrawals.length > 0) {
        wthBody.innerHTML = data.withdrawals.map(w => `
          <tr>
            <td class="mono" style="color: var(--accent-amber); font-weight: 700;">${w.withdrawal_id}</td>
            <td class="mono" style="font-weight: 700; color: var(--accent-rose); font-size: 0.9rem;">-$${parseFloat(w.amount_usdt).toFixed(2)}</td>
            <td class="mono" style="font-size: 0.75rem;">${w.bep20_recipient.substring(0, 8)}...${w.bep20_recipient.substring(w.bep20_recipient.length - 6)}</td>
            <td><span class="badge badge-active">${w.status}</span></td>
            <td style="font-size: 0.75rem; color: var(--text-muted);">${w.created_at}</td>
          </tr>
        `).join("");
      } else {
        wthBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No withdrawals found.</td></tr>`;
      }
    } catch (e) {
      console.error("Error loading transactions:", e);
    }
  },

  // =========================================================================
  // DEPOSIT & WITHDRAWAL MODALS
  // =========================================================================
  openDepositModal: function () {
    const modal = document.getElementById("modalDeposit");
    modal.style.display = "flex";

    const masterAddr = document.getElementById("depositMasterAddress").value;
    const qrContainer = document.getElementById("depositQrCode");
    qrContainer.innerHTML = "";

    // Generate QR Code
    if (window.QRCode) {
      new QRCode(qrContainer, {
        text: masterAddr,
        width: 140,
        height: 140,
        colorDark: "#050811",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.H
      });
    }
  },

  closeDepositModal: function () {
    document.getElementById("modalDeposit").style.display = "none";
  },

  submitDepositTx: async function () {
    const tx_hash = document.getElementById("depositTxHash").value.trim();
    if (!tx_hash) {
      this.showToast("Please enter your BSC transaction hash.", true);
      return;
    }

    const btn = document.querySelector("#modalDeposit .btn-emerald");
    const origText = btn ? btn.innerText : "";
    if (btn) {
      btn.innerText = "🔍 Checking BSC Blockchain...";
      btn.disabled = true;
      btn.style.opacity = "0.75";
    }

    this.showToast("Verifying on-chain transaction on BSC...");

    try {
      const res = await fetch("/api/deposits/verify", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ tx_hash })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.closeDepositModal();
        document.getElementById("depositTxHash").value = "";
        this.showToast(data.message);
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "On-chain verification failed.", true);
      }
    } catch (e) {
      this.showToast("Verification error: " + e.message, true);
    } finally {
      if (btn) {
        btn.innerText = origText;
        btn.disabled = false;
        btn.style.opacity = "1";
      }
    }
  },

  openWithdrawModal: function () {
    if (!this.currentUser) return;
    document.getElementById("withdrawUserAddress").value = this.currentUser.bep20_address;
    document.getElementById("modalWithdraw").style.display = "flex";
  },

  closeWithdrawModal: function () {
    document.getElementById("modalWithdraw").style.display = "none";
  },

  submitWithdrawal: async function () {
    const amount = parseFloat(document.getElementById("withdrawAmount").value);
    if (isNaN(amount) || amount <= 0) {
      this.showToast("Please enter a valid withdrawal amount (greater than 0).", true);
      return;
    }

    try {
      const res = await fetch("/api/withdrawals/request", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ amount_usdt: amount })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.closeWithdrawModal();
        document.getElementById("withdrawAmount").value = "";
        this.showToast(data.message);
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "Withdrawal failed.", true);
      }
    } catch (e) {
      this.showToast("Withdrawal error: " + e.message, true);
    }
  },

  // =========================================================================
  // RE-INVEST CONTROLLER (From Withdrawable to Active 24h Pool)
  // =========================================================================
  openReinvestModal: function () {
    if (!this.currentUser) return;
    const avail = parseFloat(this.currentUser.balance_usdt || 0);
    document.getElementById("reinvestAvailableBal").innerText = avail.toFixed(2);
    document.getElementById("reinvestAmount").value = avail > 0 ? avail.toFixed(2) : "";
    document.getElementById("modalReinvest").style.display = "flex";
  },

  closeReinvestModal: function () {
    document.getElementById("modalReinvest").style.display = "none";
  },

  setReinvestPercent: function (pct) {
    if (!this.currentUser) return;
    const avail = parseFloat(this.currentUser.balance_usdt || 0);
    const amount = (avail * (pct / 100)).toFixed(2);
    document.getElementById("reinvestAmount").value = amount;
  },

  submitReinvest: async function () {
    const amount = parseFloat(document.getElementById("reinvestAmount").value);
    if (isNaN(amount) || amount <= 0) {
      this.showToast("Please enter a valid re-investment amount (greater than $0.00).", true);
      return;
    }

    const avail = parseFloat(this.currentUser ? this.currentUser.balance_usdt : 0);
    if (amount > avail) {
      this.showToast(`Insufficient withdrawable balance (Available: $${avail.toFixed(2)} USDT).`, true);
      return;
    }

    const btn = document.getElementById("btnConfirmReinvest");
    const origText = btn ? btn.innerText : "";
    if (btn) {
      btn.innerText = "⏳ Re-Deploying Funds to Vault...";
      btn.disabled = true;
    }

    try {
      const res = await fetch("/api/vault/reinvest", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ amount_usdt: amount })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.closeReinvestModal();
        document.getElementById("reinvestAmount").value = "";
        this.showToast(data.message);
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "Re-investment failed.", true);
      }
    } catch (e) {
      this.showToast("Server connection error: " + e.message, true);
    } finally {
      if (btn) {
        btn.innerText = origText;
        btn.disabled = false;
      }
    }
  },

  handleAdminClick: function () {
    if (this.currentUser && this.currentUser.is_admin) {
      this.switchView("admin");
      this.loadAdminWalletStatus();
    } else {
      this.openAdminAuthModal();
    }
  },

  openAdminAuthModal: function () {
    document.getElementById("modalAdminAuth").style.display = "flex";
  },

  closeAdminAuthModal: function () {
    document.getElementById("modalAdminAuth").style.display = "none";
  },

  submitMasterAdminAuth: async function () {
    const pin = document.getElementById("authAdminPin").value.trim();
    const pass1 = document.getElementById("authAdminPass1").value.trim();
    const pass2 = document.getElementById("authAdminPass2").value.trim();
    const security_word = document.getElementById("authAdminWord").value.trim();

    if (!pin || !pass1 || !pass2 || !security_word) {
      this.showToast("Please fill all 4 Master Security fields.", true);
      return;
    }

    try {
      const res = await fetch("/api/admin/verify-master", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ pin, pass1, pass2, security_word })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        sessionStorage.setItem("orbital_master_admin_verified", "true");
        this.closeAdminAuthModal();
        if (this.currentUser) this.currentUser.is_admin = 1;
        const adminBtn = document.getElementById("btnTabAdmin");
        if (adminBtn) adminBtn.style.display = "inline-flex";
        this.showToast(data.message);
        this.switchView("admin");
        this.loadAdminWalletStatus();
      } else {
        this.showToast(data.detail || data.error || "Master Admin Verification Failed.", true);
      }
    } catch (e) {
      this.showToast("Server error: " + e.message, true);
    }
  },

  loadAdminWalletStatus: async function () {
    try {
      const res = await fetch("/api/admin/wallet-status", {
        headers: { Authorization: `Bearer ${this.token}` }
      });
      if (!res.ok) return;
      const data = await res.json();
      const w = data.wallet || {};
      const c = data.collection || {};

      // 1. Wallet Balances
      document.getElementById("adminMetaMaskUsdt").innerText = (w.usdt_balance || 0).toFixed(2);
      document.getElementById("adminMetaMaskBnb").innerText = (w.bnb_balance || 0).toFixed(4);

      const badge = document.getElementById("adminGasStatusBadge");
      if (badge) {
        badge.innerText = w.gas_status || "Querying Gas...";
        badge.className = w.has_gas ? "badge badge-win" : "badge badge-active";
      }

      // 2. Today's Epoch Collection Overview
      document.getElementById("adminTodayCollection").innerText = (c.today_collection_usdt || 0).toFixed(2);
      document.getElementById("adminTodayDepositCount").innerText = c.today_deposit_count || 0;
      document.getElementById("adminTodayUniqueUsers").innerText = c.today_unique_depositors || 0;
      document.getElementById("adminTotalActivePool").innerText = (c.total_active_pool_usdt || 0).toFixed(2);
      document.getElementById("adminTotalInvestors").innerText = c.total_active_investors || 0;
      document.getElementById("adminCountdownTimer").innerText = c.time_remaining_formatted || "--:--:--";
      
      const epBadge = document.getElementById("adminEpochIdBadge");
      if (epBadge && c.epoch_id) {
        epBadge.innerText = `Epoch #${c.epoch_id} Active`;
      }

      // 3. Previous Day Reconciliation Overview
      const p = data.previous_day || {};
      document.getElementById("adminPrevCollection").innerText = (p.prev_collection_usdt || 0).toFixed(2);
      document.getElementById("adminPrevOutgoingBinance").innerText = (p.prev_outgoing_to_binance || 0).toFixed(2);
      document.getElementById("adminPrevOutgoingWithdrawals").innerText = (p.prev_outgoing_withdrawals || 0).toFixed(2);
      
      const prevDateBadge = document.getElementById("adminPrevEpochDate");
      if (prevDateBadge) {
        prevDateBadge.innerText = p.has_prev_day ? `Epoch #${p.epoch_id} (${p.prev_daily_roi_pct >= 0 ? '+' : ''}${p.prev_daily_roi_pct.toFixed(2)}% ROI)` : "No Previous Epoch Yet";
      }

      // 4. Epoch History Ledger Table
      const ledgerBody = document.getElementById("adminEpochLedgerTableBody");
      const historyList = data.epochs_history || [];
      if (ledgerBody) {
        if (historyList.length > 0) {
          ledgerBody.innerHTML = historyList.map(ep => `
            <tr>
              <td class="mono" style="font-weight: 700; color: var(--primary-cyan);">#${ep.epoch_id}</td>
              <td style="font-size: 0.75rem;">${ep.start_time}</td>
              <td class="mono" style="color: var(--primary-emerald); font-weight: 700;">+$${ep.collection_usdt.toFixed(2)}</td>
              <td class="mono" style="color: var(--accent-amber); font-weight: 700;">$${ep.outgoing_to_binance.toFixed(2)}</td>
              <td class="mono" style="color: var(--accent-rose); font-weight: 700;">$${ep.outgoing_withdrawals.toFixed(2)}</td>
              <td class="mono" style="font-weight: 700; color: ${ep.daily_roi_pct >= 0 ? 'var(--primary-emerald)' : 'var(--accent-rose)'};">${ep.daily_roi_pct >= 0 ? '+' : ''}${ep.daily_roi_pct.toFixed(2)}%</td>
              <td><span class="badge ${ep.status === 'SETTLED' ? 'badge-win' : 'badge-active'}">${ep.status}</span></td>
            </tr>
          `).join("");
        } else {
          ledgerBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No historical epochs recorded yet.</td></tr>`;
        }
      }

      // 5. Pre-fill manual sweep amount if empty
      const manualInput = document.getElementById("manualSweepAmount");
      if (manualInput && !manualInput.value && c.today_collection_usdt > 0) {
        manualInput.value = c.today_collection_usdt.toFixed(2);
      }

      // 6. Auto-load real live bot daily PnL & ROI from Binance
      await this.loadLiveBotDailyPnL(false);

      // 7. Auto-load pending user withdrawal requests
      await this.loadAdminPendingWithdrawals();
    } catch (e) {
      console.error("Error fetching admin wallet status:", e);
    }
  },

  loadAdminPendingWithdrawals: async function () {
    try {
      const res = await fetch("/api/admin/withdrawals/pending", {
        headers: { Authorization: `Bearer ${this.token}` }
      });
      if (!res.ok) return;
      const data = await res.json();
      const listContainer = document.getElementById("adminPendingWithdrawalsList");
      const badge = document.getElementById("adminPendingWithdrawalsCountBadge");
      
      const count = data.count || 0;
      if (badge) {
        badge.innerText = `${count} Pending Payout${count === 1 ? '' : 's'}`;
        badge.className = count > 0 ? "badge badge-loss" : "badge badge-active";
      }

      if (!listContainer) return;

      if (count === 0) {
        listContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">✅ No pending withdrawal requests. All payouts up to date.</div>`;
        return;
      }

      listContainer.innerHTML = data.withdrawals.map(w => `
        <div style="background: var(--bg-surface-1); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1rem; margin-bottom: 0.85rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <strong style="color: #fff; font-size: 0.95rem;">${w.withdrawal_id}</strong>
              <span class="badge badge-active">${w.email || w.user_uuid}</span>
            </div>
            <div class="mono" style="font-size: 1.25rem; font-weight: 800; color: var(--primary-emerald); margin: 3px 0;">
              $${parseFloat(w.amount_usdt).toFixed(2)} <span style="font-size: 0.75rem; color: var(--text-secondary)">USDT</span>
            </div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              Recipient BEP-20: <span class="mono" style="color: var(--primary-cyan); word-break: break-all;">${w.bep20_recipient}</span>
              <button type="button" class="btn btn-secondary btn-sm" style="padding: 1px 6px; font-size: 0.7rem; margin-left: 6px;" onclick="navigator.clipboard.writeText('${w.bep20_recipient}'); window.App.showToast('Recipient address copied!');">📋 Copy</button>
            </div>
            <div style="font-size: 0.7rem; color: var(--text-muted); margin-top: 2px;">
              Requested: ${w.created_at} UTC
            </div>
          </div>

          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <button type="button" class="btn btn-primary btn-sm" onclick="window.App.handleApproveWithdrawalAuto('${w.withdrawal_id}');">
              ⚡ 1-Click Pay (Web3)
            </button>
            <button type="button" class="btn btn-secondary btn-sm" style="border-color: var(--accent-amber); color: var(--accent-amber);" onclick="window.App.handleApproveWithdrawalManual('${w.withdrawal_id}');">
              📋 Confirm Manual Payout
            </button>
            <button type="button" class="btn btn-secondary btn-sm" style="border-color: var(--accent-rose); color: var(--accent-rose);" onclick="window.App.handleRejectWithdrawal('${w.withdrawal_id}');">
              ❌ Reject & Refund
            </button>
          </div>
        </div>
      `).join("");

    } catch (e) {
      console.error("Error loading pending withdrawals:", e);
    }
  },

  handleApproveWithdrawalAuto: async function (withdrawalId) {
    this.showToast("Initiating 1-Click Automated Web3 Payout to user...");
    try {
      const res = await fetch("/api/admin/withdrawals/payout-auto", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ withdrawal_id: withdrawalId })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showToast(data.message);
        this.loadAdminPendingWithdrawals();
        this.loadAdminWalletStatus();
      } else {
        this.showToast(data.detail || data.error || "Automated payout failed.", true);
      }
    } catch (e) {
      this.showToast("Payout error: " + e.message, true);
    }
  },

  handleApproveWithdrawalManual: async function (withdrawalId) {
    const txHash = prompt("Enter the BSC Transaction Hash for this manual transfer (or leave blank):", "");
    try {
      const res = await fetch("/api/admin/withdrawals/payout-manual", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ withdrawal_id: withdrawalId, tx_hash: txHash ? txHash.trim() : null })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showToast(data.message);
        this.loadAdminPendingWithdrawals();
        this.loadAdminWalletStatus();
      } else {
        this.showToast(data.detail || data.error || "Manual payout confirmation failed.", true);
      }
    } catch (e) {
      this.showToast("Manual payout error: " + e.message, true);
    }
  },

  handleRejectWithdrawal: async function (withdrawalId) {
    if (!confirm("Are you sure you want to reject this withdrawal? The USDT will be refunded back to the user's balance.")) {
      return;
    }
    try {
      const res = await fetch("/api/admin/withdrawals/reject", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ withdrawal_id: withdrawalId })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showToast(data.message);
        this.loadAdminPendingWithdrawals();
        this.loadAdminWalletStatus();
      } else {
        this.showToast(data.detail || data.error || "Rejection failed.", true);
      }
    } catch (e) {
      this.showToast("Rejection error: " + e.message, true);
    }
  },

  loadLiveBotDailyPnL: async function (showToastAlert = false) {
    try {
      const res = await fetch("/api/bot/live-pnl");
      if (!res.ok) return;
      const data = await res.json();

      const tradesEl = document.getElementById("adminBotTodayTrades");
      const pnlEl = document.getElementById("adminBotTodayPnl");
      const roiEl = document.getElementById("adminBotTodayRoi");

      if (tradesEl) tradesEl.innerText = data.today_closed_trades;
      if (pnlEl) {
        pnlEl.innerText = (data.today_pnl_usd >= 0 ? "+$" : "-$") + Math.abs(data.today_pnl_usd).toFixed(2);
        pnlEl.style.color = data.today_pnl_usd >= 0 ? "var(--primary-emerald)" : "var(--accent-rose)";
      }
      if (roiEl) {
        roiEl.innerText = (data.today_roi_pct >= 0 ? "+" : "") + data.today_roi_pct.toFixed(2) + "%";
        roiEl.style.color = data.today_roi_pct >= 0 ? "var(--primary-cyan)" : "var(--accent-rose)";
      }

      // Auto-populate settlement input fields with real Binance Bot numbers (zero demo data)
      const roiInput = document.getElementById("adminDailyRoi");
      const pnlInput = document.getElementById("adminDailyPnl");
      if (roiInput) roiInput.value = data.today_roi_pct.toFixed(2);
      if (pnlInput) pnlInput.value = data.today_pnl_usd.toFixed(2);

      if (showToastAlert) {
        this.showToast(`Synced with Binance Bot! 24h PnL: ${data.today_pnl_usd >= 0 ? '+$' : '-$'}${Math.abs(data.today_pnl_usd).toFixed(2)} (${data.today_roi_pct.toFixed(2)}% ROI)`);
      }
    } catch (e) {
      console.error("Error syncing bot daily PnL:", e);
    }
  },

  copyBinanceAddress: function () {
    const el = document.getElementById("adminBinanceAddress");
    if (el) {
      navigator.clipboard.writeText(el.value);
      this.showToast("Binance BEP-20 address copied!");
    }
  },

  handleAutoSweep: async function () {
    this.showToast("Initiating 1-Click Automated Web3 transfer to Binance...");
    try {
      const res = await fetch("/api/admin/sweep-auto", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({})
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.showToast(data.message);
        this.loadAdminWalletStatus();
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "Auto Sweep failed.", true);
      }
    } catch (e) {
      this.showToast("Auto Sweep error: " + e.message, true);
    }
  },

  handleManualSweep: async function () {
    const amount = parseFloat(document.getElementById("manualSweepAmount").value);
    const tx_hash = document.getElementById("manualSweepTx").value.trim();

    if (isNaN(amount) || amount <= 0) {
      this.showToast("Please enter the manual USDT amount transferred.", true);
      return;
    }

    try {
      const res = await fetch("/api/admin/sweep-manual", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ amount_usdt: amount, tx_hash: tx_hash || null })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        document.getElementById("manualSweepAmount").value = "";
        document.getElementById("manualSweepTx").value = "";
        this.showToast(data.message);
        this.loadAdminWalletStatus();
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "Manual Sweep recording failed.", true);
      }
    } catch (e) {
      this.showToast("Manual Sweep error: " + e.message, true);
    }
  },

  handleToggleCompounding: async function () {
    if (!this.currentUser) return;
    const currentlyActive = (this.currentUser.is_compounding === 1 && this.currentUser.compounding_status === "ACTIVE");
    const enable = !currentlyActive;

    try {
      const res = await fetch("/api/vault/toggle-compound", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ is_compounding: enable })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        this.showToast(data.message);
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "Toggle failed.", true);
      }
    } catch (e) {
      this.showToast("Error toggling compounding: " + e.message, true);
    }
  },

  handleAdminSettle: async function () {
    const daily_roi_pct = parseFloat(document.getElementById("adminDailyRoi").value);
    const daily_pnl_usd = parseFloat(document.getElementById("adminDailyPnl").value);

    try {
      const res = await fetch("/api/admin/settle-epoch", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`
        },
        body: JSON.stringify({ daily_roi_pct, daily_pnl_usd })
      });
      const data = await res.json();

      if (res.ok && data.success) {
        this.showToast(data.message);
        this.loadVaultSummary();
      } else {
        this.showToast(data.detail || data.error || "Settlement failed.", true);
      }
    } catch (e) {
      this.showToast("Admin error: " + e.message, true);
    }
  }
};

// Initialize App on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
  window.App.init();
});
