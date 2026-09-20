<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">B</div>
        <div>
          <strong>Bambu Timelapse</strong>
          <small>Cloud capture service</small>
        </div>
      </div>

      <nav>
        <RouterLink to="/">Dashboard</RouterLink>
        <RouterLink to="/jobs">Jobs</RouterLink>
        <RouterLink to="/devices">Devices</RouterLink>
        <RouterLink to="/settings">Settings</RouterLink>
      </nav>

      <div class="sidebar-footer">
        <span class="dot"></span>
        v0.2.0
      </div>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>
