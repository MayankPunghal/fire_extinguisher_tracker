// static/js/navbar.js

(function() {
    "use strict";

    document.addEventListener('DOMContentLoaded', () => {
        const navbarToggleBtn = document.getElementById('navbarToggler');
        const sidebar = document.getElementById('navbarMenu');
        const overlay = document.getElementById('sidebarOverlay');
        const body = document.body;

        if (!navbarToggleBtn || !sidebar || !overlay) {
            console.error("Navbar JS Error: Crucial elements missing.");
            return;
        }

        function openSidebar() {
            if (!body.classList.contains('sidebar-open')) {
                body.classList.add('sidebar-open');
                overlay.classList.add('visible');
                navbarToggleBtn.setAttribute('aria-expanded', 'true');
                console.log("Sidebar opened");
            }
        }

        function closeSidebar() {
            if (body.classList.contains('sidebar-open')) {
                body.classList.remove('sidebar-open');
                overlay.classList.remove('visible');
                navbarToggleBtn.setAttribute('aria-expanded', 'false');
                console.log("Sidebar closed");
            }
        }

        // Toggle button click listener - KEEP
        navbarToggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = body.classList.contains('sidebar-open');
            if (isOpen) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });

        // Overlay click listener - KEEP
        overlay.addEventListener('click', () => {
            closeSidebar();
        });

        // Escape key listener - KEEP
        document.addEventListener('keydown', (e) => {
            if (e.key === "Escape" && body.classList.contains('sidebar-open')) {
                closeSidebar();
            }
        });

        // --- REMOVE THIS ENTIRE BLOCK ---
        // sidebar.addEventListener('click', (e) => {
        //      if (e.target.matches('a.nav-link')) {
        //          console.log("Link inside sidebar clicked:", e.target.href);
        //          // Allow default link navigation to proceed.
        //          // Close the sidebar - the navigation will likely happen before animation finishes
        //          closeSidebar(); // <<< THIS WAS CAUSING THE PROBLEM
        //      }
        // });
        // --- END REMOVAL ---

        console.log("Responsive Navbar JS Initialized.");
    });

})();