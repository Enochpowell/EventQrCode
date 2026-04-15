// static/js/main.js

document.addEventListener('DOMContentLoaded', function() {
    // --- Navbar Toggle for Mobile ---
    const menuToggle = document.querySelector('.menu-toggle');
    const navLinks = document.querySelector('.navbar-links');

    if (menuToggle && navLinks) {
        menuToggle.addEventListener('click', function() {
            navLinks.classList.toggle('active');
        });
    }


    // --- Seat Availability Check for Individual Form (Reactive) ---
    const tableInput = document.getElementById('table_number');
    const seatInput = document.getElementById('seat_number');
    const seatStatusDiv = document.getElementById('seat-status');
    const generateButton = document.querySelector('#individual-form button[type="submit"]'); // Target specific form's button

    if (tableInput && seatInput && seatStatusDiv && generateButton) {
        let debounceTimer;

        const checkAvailability = async () => {
            const table_num = tableInput.value.trim();
            const seat_num = parseInt(seatInput.value);

            seatStatusDiv.textContent = ''; // Clear previous message
            seatStatusDiv.className = 'seat-status'; // Reset classes, keep base
            generateButton.disabled = true; // Disable button by default

            if (table_num === '' || isNaN(seat_num) || seat_num < 1) {
                seatStatusDiv.textContent = 'Please enter valid table and seat numbers.';
                seatStatusDiv.classList.add('info-status');
                return;
            }

            seatStatusDiv.textContent = 'Checking availability...';
            seatStatusDiv.classList.add('checking-status');

            try {
                // Encode table_num to handle spaces or special characters in URL
                const encodedTableNum = encodeURIComponent(table_num);
                const response = await fetch(`/api/check_seat_availability/${encodedTableNum}/${seat_num}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();

                if (data.is_booked) {
                    let message = `Table ${data.table_number}, Seat ${data.seat_number} is BOOKED.`;
                    if (data.booked_by) {
                        message += ` (Booked by: ${data.booked_by})`;
                    }
                    seatStatusDiv.textContent = message;
                    seatStatusDiv.classList.add('error-status');
                    generateButton.disabled = true;
                } else {
                    seatStatusDiv.textContent = `Table ${data.table_number}, Seat ${data.seat_number} is AVAILABLE.`;
                    seatStatusDiv.classList.add('success-status');
                    generateButton.disabled = false; // Enable button
                }
            } catch (error) {
                console.error('Error checking seat availability:', error);
                seatStatusDiv.textContent = 'Error checking seat. Please try again.';
                seatStatusDiv.classList.add('error-status');
                generateButton.disabled = true;
            }
        };

        // Debounce input to avoid too many requests
        tableInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(checkAvailability, 500); // Wait 500ms after last input
        });
        seatInput.addEventListener('input', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(checkAvailability, 500); // Wait 500ms after last input
        });

        // Initial check if fields are pre-filled (e.g., after a form error)
        if (tableInput.value !== '' && seatInput.value !== '') {
            checkAvailability();
        }
    }
});