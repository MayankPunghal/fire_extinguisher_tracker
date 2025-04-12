// static/js/navbar.js

document.addEventListener('DOMContentLoaded', () => {
    const navbarToggleBtn = document.getElementById('navbarToggleBtn');
    const sidebar = document.getElementById('navbarMenu'); // The collapsible element
    const overlay = document.getElementById('sidebarOverlay');
    const body = document.body;

    // --- Add this check early ---
    if (!navbarToggleBtn || !sidebar || !overlay) {
        console.error("Navbar critical elements not found! Toggle/Sidebar functionality will fail.");
        return; // Stop if essential elements are missing
    }
    // --- End check ---

    // Function to toggle the sidebar
    const toggleSidebar = () => {
        const isOpen = body.classList.contains('sidebar-open');
        body.classList.toggle('sidebar-open');
        navbarToggleBtn.setAttribute('aria-expanded', !isOpen);
    };

    // Event listener for the toggle button
    navbarToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleSidebar();
    });

    // Event listener for the overlay (to close sidebar)
    overlay.addEventListener('click', () => {
        if (body.classList.contains('sidebar-open')) {
            toggleSidebar();
        }
    });

    // --- MODIFIED: Link Click Listener ---
    const sidebarLinks = sidebar.querySelectorAll('a.nav-link');
    console.log(`Found ${sidebarLinks.length} sidebar links.`); // Debug: Check if links are found

    sidebarLinks.forEach(link => {
        link.addEventListener('click', (event) => { // Keep event parameter
             console.log("Sidebar link clicked:", link.href); // Debug: Log the click
             // Don't prevent default navigation
             // Don't use setTimeout - let the browser navigate immediately

             // Optionally, you *could* still try to close the sidebar visually,
             // but it might not complete before navigation.
             if (body.classList.contains('sidebar-open')) {
                 // Remove the class directly - animation might not finish
                 // body.classList.remove('sidebar-open');
                 // navbarToggleBtn.setAttribute('aria-expanded', 'false');
                 // console.log("Sidebar closed immediately on link click (animation may cut short).");

                 // OR just let navigation happen without touching the sidebar state here.
                 // The page reload will reset it anyway.
             }
        });
    });
    // --- END MODIFICATION ---


    // Optional: Close sidebar if user presses Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === "Escape" && body.classList.contains('sidebar-open')) {
            toggleSidebar();
        }
    });

}); // End DOMContentLoaded