document.addEventListener('DOMContentLoaded', function() {
    const addNewBtn = document.getElementById('addNewBtn');
    const addNewDropdown = document.getElementById('addNewDropdown');
    const addNewMenuDiv = addNewBtn ? addNewBtn.closest('.add-new-menu') : null;

    if (addNewBtn && addNewDropdown && addNewMenuDiv) {
        addNewBtn.addEventListener('click', function(event) {
            event.stopPropagation(); // Prevent click from closing it immediately if also listening on document
            addNewMenuDiv.classList.toggle('active');
        });

        // Optional: Close dropdown if clicking outside of it
        document.addEventListener('click', function(event) {
            if (addNewMenuDiv && addNewMenuDiv.classList.contains('active') && !addNewMenuDiv.contains(event.target)) {
                addNewMenuDiv.classList.remove('active');
            }
        });
    }
});