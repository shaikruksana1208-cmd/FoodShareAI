const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector(".primary-nav");
const toast = document.querySelector(".toast");
let toastTimer;
let searchTimer;
let csrfToken = "";
let currentUser = null;

function closeMenu() {
  menuButton.setAttribute("aria-expanded", "false");
  menuButton.setAttribute("aria-label", "Open navigation");
  navigation.classList.remove("is-open");
}
async function loadMyDonations() {
  const section = document.getElementById("owned-donations");
  const list = document.getElementById("owned-donation-list");
  if (!currentUser || !["donor", "admin"].includes(currentUser.role)) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  list.replaceChildren();
  setMessage("owned-donations-message", "Loading your saved listings…");
  try {
    const { donations } = await api("/api/my/donations");
    if (!donations.length) {
      setMessage("owned-donations-message", "You have not submitted any listings yet.");
      return;
    }
    donations.forEach((donation) => {
      const row = document.createElement("div");
      row.className = "owned-donation-row";
      const description = document.createElement("span");
      description.textContent = `${donation.food_name} · ${donation.quantity_available} ${donation.unit} available · ${donation.quantity_reserved} ${donation.unit} reserved · ${donation.lifecycle_status}`;
      row.append(description);
      if (donation.status !== "completed") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button button-secondary";
        button.textContent = donation.status === "available" ? "Mark unavailable" : "Make available";
        button.addEventListener("click", async () => {
          button.disabled = true;
          const nextStatus = donation.status === "available" ? "unavailable" : "available";
          try {
            await api(`/api/donations/${donation.id}/status`, {
              method: "PATCH", body: JSON.stringify({ status: nextStatus }),
            });
            await Promise.all([loadMyDonations(), loadListings(), loadRecommendations(), loadDashboard()]);
            showToast(`Listing marked ${nextStatus}.`);
          } catch (error) {
            button.disabled = false;
            showToast(error.message);
          }
        });
        row.append(button);
      }
      list.append(row);
    });
    setMessage("owned-donations-message", `${donations.length} saved listing${donations.length === 1 ? "" : "s"}.`);
  } catch (error) {
    setMessage("owned-donations-message", error.message, "error");
  }
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("is-visible");
  toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3600);
}

menuButton.addEventListener("click", () => {
  const isOpen = menuButton.getAttribute("aria-expanded") === "true";
  menuButton.setAttribute("aria-expanded", String(!isOpen));
  menuButton.setAttribute("aria-label", isOpen ? "Open navigation" : "Close navigation");
  navigation.classList.toggle("is-open", !isOpen);
});

navigation.addEventListener("click", (event) => {
  if (event.target.closest("a")) closeMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
    closeMenu();
    menuButton.focus();
  }
});

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (["POST", "PATCH", "DELETE"].includes(options.method)) headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function formObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function setMessage(id, message, kind = "") {
  const element = document.getElementById(id);
  element.textContent = message;
  element.classList.toggle("is-error", kind === "error");
  element.classList.toggle("is-success", kind === "success");
}

function createLabel(text) {
  const element = document.createElement("span");
  element.textContent = text;
  return element;
}

function renderListing(donation) {
  const article = document.createElement("article");
  article.className = "listing-card live-listing-card";
  const content = document.createElement("div");
  content.className = "listing-content";
  const metadata = document.createElement("div");
  metadata.className = "listing-meta";
  const category = createLabel(donation.category);
  category.className = "food-tag";
  const status = createLabel(`${donation.quantity_available} ${donation.unit} available`);
  status.className = "pickup-time";
  metadata.append(category, status);
  const title = document.createElement("h3");
  title.textContent = donation.food_name;
  const details = document.createElement("p");
  details.textContent = `${donation.location} · Best before ${new Date(donation.expires_at).toLocaleString()}`;
  content.append(metadata, title, details);
  if (currentUser && ["donor", "admin"].includes(currentUser.role)) {
    const statusButton = document.createElement("button");
    statusButton.type = "button";
    statusButton.className = "text-link listing-status-button";
    statusButton.textContent = "Mark unavailable";
    statusButton.addEventListener("click", async () => {
      statusButton.disabled = true;
      try {
        await api(`/api/donations/${donation.id}/status`, {
          method: "PATCH", body: JSON.stringify({ status: "unavailable" }),
        });
        showToast("Donation marked unavailable.");
        await Promise.all([loadListings(), loadMyDonations(), loadDashboard()]);
      } catch (error) {
        statusButton.disabled = false;
        showToast(error.message);
      }
    });
    content.append(statusButton);
  }
  article.append(content);
  return article;
}

async function loadListings() {
  const grid = document.getElementById("listing-grid");
  setMessage("listing-message", "Loading available food…");
  grid.replaceChildren();
  const params = new URLSearchParams();
  const query = document.getElementById("food-search").value.trim();
  const category = document.getElementById("food-category").value;
  if (query) params.set("q", query);
  if (category) params.set("category", category);
  try {
    const { donations } = await api(`/api/donations?${params}`);
    if (!donations.length) {
      setMessage("listing-message", "No available food matches those filters yet.");
      return;
    }
    grid.replaceChildren(...donations.map(renderListing));
    setMessage("listing-message", `${donations.length} available listing${donations.length === 1 ? "" : "s"}.`);
  } catch (error) {
    setMessage("listing-message", `${error.message}. Check that the Flask app is running.`, "error");
  }
}

function renderAuthPanel() {
  const panel = document.getElementById("auth-panel");
  panel.replaceChildren();
  if (currentUser) {
    const heading = document.createElement("p");
    heading.textContent = `Signed in as ${currentUser.name} (${currentUser.role}).`;
    const logout = document.createElement("button");
    logout.type = "button";
    logout.className = "button button-secondary";
    logout.textContent = "Log out";
    logout.addEventListener("click", async () => {
      try {
        await api("/api/logout", { method: "POST", body: "{}" });
        currentUser = null;
        await initializeApp();
        showToast("You are signed out.");
      } catch (error) {
        showToast(error.message);
      }
    });
    panel.append(heading, logout);
    return;
  }
  const form = document.createElement("form");
  form.className = "auth-form";
  form.innerHTML = '<label>Your name<input name="name" autocomplete="name" required maxlength="100"></label><label>Email<input name="email" type="email" autocomplete="email" required maxlength="254"></label><label>Password<input name="password" type="password" autocomplete="new-password" required minlength="8" maxlength="128"></label><label>Account type<select name="role"><option value="donor">Food donor</option><option value="recipient">Food recipient</option></select></label><button class="button button-primary" type="submit">Create account</button><button class="button button-secondary" type="button">Log in</button><p class="api-message" role="status" aria-live="polite"></p>';
  const message = form.querySelector('[role="status"]');
  const loginButton = form.querySelector('button[type="button"]');
  const submit = async (isLogin) => {
    const data = formObject(form);
    const endpoint = isLogin ? "/api/login" : "/api/register";
    try {
      const result = await api(endpoint, { method: "POST", body: JSON.stringify(data) });
      currentUser = result.user;
      await initializeApp();
      showToast(isLogin ? "Welcome back." : "Account created.");
    } catch (error) {
      message.textContent = error.message;
      message.classList.add("is-error");
    }
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(false);
  });
  loginButton.addEventListener("click", () => submit(true));
  panel.append(form);
}

async function loadRequests() {
  const select = document.getElementById("match-request");
  select.replaceChildren(new Option("Choose an open request", ""));
  const history = document.getElementById("request-history");
  if (!currentUser || !["recipient", "admin"].includes(currentUser.role)) {
    history.hidden = true;
    return;
  }
  history.hidden = false;
  try {
    const { requests } = await api("/api/requests");
    requests.filter((item) => item.status === "open").forEach((item) => {
      select.add(new Option(`${item.category} · ${item.quantity} ${item.unit} · ${item.location}`, item.id));
    });
    renderRequestHistory(requests);
  } catch (error) {
    setMessage("matching-message", error.message, "error");
    setMessage("request-history-message", error.message, "error");
  }
}

function renderRequestHistory(requests) {
  const list = document.getElementById("request-history-list");
  list.replaceChildren();
  if (!requests.length) {
    setMessage("request-history-message", "You do not have any requests yet.");
    return;
  }
  requests.forEach((foodRequest) => {
    const row = document.createElement("article");
    row.className = "request-history-row";
    const title = document.createElement("h4");
    title.textContent = `Request #${foodRequest.id} · ${foodRequest.category} · ${foodRequest.quantity} ${foodRequest.unit}`;
    const status = document.createElement("span");
    status.className = `status-badge status-${foodRequest.status}`;
    status.textContent = foodRequest.status;
    const details = document.createElement("p");
    details.textContent = foodRequest.allocation
      ? `Donation: ${foodRequest.allocation.food_name} · ${foodRequest.allocation.quantity} ${foodRequest.allocation.unit}`
      : `Pickup area: ${foodRequest.location}`;
    row.append(title, status, details);

    if (foodRequest.status === "reserved" && foodRequest.allocation?.status === "reserved") {
      const actions = document.createElement("div");
      actions.className = "request-history-actions";
      const confirm = document.createElement("button");
      confirm.type = "button";
      confirm.className = "button button-primary";
      confirm.textContent = "Confirm food collected";
      confirm.addEventListener("click", async () => {
        confirm.disabled = true;
        try {
          await api(`/api/allocations/${foodRequest.allocation.id}/collect`, {
            method: "POST", body: "{}",
          });
          setMessage("request-message", "Collection confirmed. The dashboard now counts this quantity as collected.", "success");
          await Promise.all([loadRequests(), loadListings(), loadDashboard()]);
          await loadRecommendations();
        } catch (error) {
          confirm.disabled = false;
          setMessage("request-message", error.message, "error");
        }
      });
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "button button-secondary";
      cancel.textContent = "Cancel reservation";
      cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try {
          await api(`/api/requests/${foodRequest.id}/cancel`, {
            method: "POST", body: JSON.stringify({ reason: "Cancelled by requester" }),
          });
          setMessage("request-message", "Reservation cancelled and available quantity restored.", "success");
          await Promise.all([loadRequests(), loadListings(), loadDashboard()]);
          await loadRecommendations();
        } catch (error) {
          cancel.disabled = false;
          setMessage("request-message", error.message, "error");
        }
      });
      actions.append(confirm, cancel);
      row.append(actions);
    } else if (foodRequest.status === "open") {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "button button-secondary";
      cancel.textContent = "Cancel request";
      cancel.addEventListener("click", async () => {
        cancel.disabled = true;
        try {
          await api(`/api/requests/${foodRequest.id}/cancel`, {
            method: "POST", body: JSON.stringify({ reason: "Cancelled by requester" }),
          });
          setMessage("request-message", "Request cancelled.", "success");
          await Promise.all([loadRequests(), loadDashboard()]);
          await loadRecommendations();
        } catch (error) {
          cancel.disabled = false;
          setMessage("request-message", error.message, "error");
        }
      });
      row.append(cancel);
    }
    list.append(row);
  });
  setMessage("request-history-message", `${requests.length} request${requests.length === 1 ? "" : "s"}.`);
}

function renderRecommendation(item, canAccept) {
  const article = document.createElement("article");
  article.className = "recommendation-item";
  const heading = document.createElement("h3");
  heading.textContent = `Donation #${item.donation_id} · ${item.compatibility_score}/100`;
  const reasons = document.createElement("ul");
  item.match_reasons.forEach((reason) => {
    const entry = document.createElement("li");
    entry.textContent = reason;
    reasons.append(entry);
  });
  const action = document.createElement("p");
  action.textContent = item.recommended_next_action;
  article.append(heading, reasons, action);
  if (canAccept) {
    const button = document.createElement("button");
    button.className = "button button-primary";
    button.type = "button";
    button.textContent = "Accept match and reserve quantity";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api(`/api/matches/${item.donation_id}/${item.request_id}/accept`, {
          method: "POST", body: "{}",
        });
        showToast("Match accepted and inventory updated.");
        await Promise.all([loadListings(), loadMyDonations(), loadRequests(), loadDashboard()]);
        await loadRecommendations();
      } catch (error) {
        button.disabled = false;
        showToast(error.message);
      }
    });
    article.append(button);
  }
  return article;
}

function renderRejectedCandidates(candidates) {
  if (!candidates.length) return null;
  const details = document.createElement("details");
  details.className = "rejected-candidates";
  const summary = document.createElement("summary");
  summary.textContent = `Why ${candidates.length} candidate pair${candidates.length === 1 ? " was" : "s were"} rejected`;
  const list = document.createElement("ul");
  candidates.slice(0, 12).forEach((candidate) => {
    const item = document.createElement("li");
    item.textContent = `Donation ${candidate.donation_id}: ${candidate.rejected_constraints.join("; ")}`;
    list.append(item);
  });
  details.append(summary, list);
  return details;
}

async function loadRecommendations() {
  const list = document.getElementById("recommendation-list");
  list.replaceChildren();
  if (!currentUser || !["recipient", "donor", "admin"].includes(currentUser.role)) {
    setMessage("matching-message", "Sign in as a donor, recipient, or administrator to see matches.");
    return;
  }
  const selectedRequest = document.getElementById("match-request").value;
  if (currentUser.role === "recipient" && !selectedRequest) {
    setMessage("matching-message", "Submit an open food request to view eligible donations.");
    return;
  }
  setMessage("matching-message", "Checking safe, available listings…");
  try {
    const query = currentUser.role === "recipient" ? `?request_id=${encodeURIComponent(selectedRequest)}` : "";
    const result = await api(`/api/matches${query}`);
    if (!result.recommendations.length) {
      setMessage("matching-message", result.message || "No safe, available match is available yet.");
      const rejected = renderRejectedCandidates(result.rejected_candidates || []);
      if (rejected) list.append(rejected);
      return;
    }
    const rows = result.recommendations.map((item) => renderRecommendation(
      item, currentUser.role === "donor" || currentUser.role === "admin",
    ));
    const rejected = renderRejectedCandidates(result.rejected_candidates || []);
    if (rejected) rows.push(rejected);
    list.replaceChildren(...rows);
    setMessage("matching-message", `${result.recommendations.length} valid recommendation${result.recommendations.length === 1 ? "" : "s"}. Invalid food is excluded.`);
  } catch (error) {
    setMessage("matching-message", error.message, "error");
  }
}

async function loadDashboard() {
  const grid = document.getElementById("dashboard-grid");
  grid.replaceChildren();
  if (!currentUser || currentUser.role !== "admin") {
    grid.hidden = true;
    setMessage("dashboard-message", "Sign in using an administrator account to view database totals.");
    return;
  }
  setMessage("dashboard-message", "Loading saved application totals…");
  try {
    const data = await api("/api/dashboard");
    const labels = {
      total_donations: "Total donations",
      available_donations: "Donations with available stock",
      reserved_donations: "Donations with reservations",
      expired_donations: "Donations with expired stock",
      completed_donations: "Fully collected donations",
      open_requests: "Open requests",
      reserved_requests: "Reserved requests",
      collected_requests: "Recipient-confirmed collected requests",
      cancelled_requests: "Cancelled requests",
      reserved_allocations: "Active reservations",
      collected_allocations: "Confirmed collections",
      cancelled_allocations: "Cancelled reservations",
    };
    Object.entries(labels).forEach(([key, label]) => {
      const card = document.createElement("div");
      card.className = "dashboard-stat";
      const value = document.createElement("strong");
      value.textContent = data.statistics[key];
      const caption = document.createElement("span");
      caption.textContent = label;
      card.append(value, caption);
      grid.append(card);
    });
    const quantityLabels = {
      quantity_available_by_unit: "Available quantity by unit",
      quantity_reserved_by_unit: "Reserved quantity by unit",
      quantity_collected_by_unit: "Recipient-confirmed collection by unit",
      quantity_cancelled_by_unit: "Cancelled reservation quantity by unit",
      quantity_expired_available_by_unit: "Expired available stock by unit",
      quantity_expired_reserved_by_unit: "Expired reserved stock by unit (collection blocked)",
    };
    Object.entries(quantityLabels).forEach(([key, label]) => {
      const card = document.createElement("div");
      card.className = "dashboard-stat";
      const value = document.createElement("strong");
      const quantities = Object.entries(data.statistics[key] || {});
      value.textContent = quantities.length
        ? quantities.map(([unit, amount]) => `${amount} ${unit}`).join(" · ")
        : "0";
      const caption = document.createElement("span");
      caption.textContent = label;
      card.append(value, caption);
      grid.append(card);
    });
    const note = document.createElement("p");
    note.className = "dashboard-disclaimer";
    note.textContent = data.note;
    grid.append(note);
    grid.hidden = false;
    setMessage("dashboard-message", "Statistics loaded from saved application records.");
  } catch (error) {
    setMessage("dashboard-message", error.message, "error");
  }
}

async function initializeApp() {
  try {
    const csrf = await api("/api/csrf");
    csrfToken = csrf.csrf_token;
    const sessionData = await api("/api/session");
    currentUser = sessionData.user;
    renderAuthPanel();
    const donorForm = document.getElementById("donation-form");
    donorForm.hidden = !(currentUser && ["donor", "admin"].includes(currentUser.role));
    const recipientForm = document.getElementById("request-form");
    recipientForm.hidden = !(currentUser && ["recipient", "admin"].includes(currentUser.role));
    await Promise.all([loadListings(), loadRequests(), loadDashboard(), loadMyDonations()]);
    await loadRecommendations();
  } catch (error) {
    setMessage("listing-message", `Backend unavailable: ${error.message}`, "error");
  }
}

document.getElementById("donation-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formObject(form);
  data.food_safe = form.elements.food_safe.checked;
  for (const key of ["prepared_at", "expires_at"]) {
    data[key] = new Date(data[key]).toISOString();
  }
  data.quantity = Number(data.quantity);
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  setMessage("donation-message", "Saving donation…");
  try {
    await api("/api/donations", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    setMessage("donation-message", "Donation saved successfully.", "success");
    await Promise.all([loadListings(), loadMyDonations(), loadDashboard()]);
  } catch (error) {
    setMessage("donation-message", error.message, "error");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("request-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = formObject(form);
  data.quantity = Number(data.quantity);
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  setMessage("request-message", "Saving request…");
  try {
    const result = await api("/api/requests", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    setMessage("request-message", `Request #${result.food_request.id} saved. Choose it in matching to see recommendations.`, "success");
    await loadRequests();
  } catch (error) {
    setMessage("request-message", error.message, "error");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("food-search").addEventListener("input", () => {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadListings, 250);
});
document.getElementById("food-category").addEventListener("change", loadListings);
document.getElementById("refresh-listings").addEventListener("click", loadListings);
document.getElementById("match-request").addEventListener("change", loadRecommendations);
document.querySelectorAll('a[href="#login"]').forEach((link) => {
  link.setAttribute("href", "#donate");
});

initializeApp();