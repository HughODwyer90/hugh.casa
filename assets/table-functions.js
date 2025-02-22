document.addEventListener('DOMContentLoaded', () => {
    let currentFilter = 'All';

    function sortTable(tableId, columnIndex) {
        const table = document.getElementById(tableId);
        const tbody = table.querySelector('tbody');
        const header = table.querySelectorAll('th')[columnIndex];
        const order = header.dataset.order === 'desc' ? 'asc' : 'desc';

        header.dataset.order = order;

        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
            const aText = a.children[columnIndex].textContent.trim().toLowerCase();
            const bText = b.children[columnIndex].textContent.trim().toLowerCase();
            return order === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText);
        });

        tbody.innerHTML = '';
        rows.forEach(row => tbody.appendChild(row));
    }

    document.querySelectorAll('th').forEach((header, index) => {
        header.style.cursor = "pointer";
        header.addEventListener('click', () => {
            const tableId = header.closest('table').id;
            sortTable(tableId, index);
        });
    });

    function filterTable(tableId, filter = 'All') {
        const query = document.getElementById('searchBox').value.toLowerCase();
        const rows = document.querySelectorAll(`#${tableId} tbody tr`);

        rows.forEach(row => {
            const entityId = row.cells[0].textContent.trim();
            const matchesFilter = filter === 'All' || entityId.charAt(0).toUpperCase() === filter;
            const matchesQuery = Array.from(row.cells).some(cell => cell.textContent.toLowerCase().includes(query));
            row.style.display = matchesFilter && matchesQuery ? '' : 'none';
        });
    }

    function applyFiltering() {
        filterTable('entitiesTable', currentFilter);
        filterTable('integrationsTable', currentFilter);
    }

    document.getElementById('searchBox').addEventListener('input', applyFiltering);

    document.querySelectorAll('.filter').forEach(filter => {
        filter.addEventListener('click', () => {
            document.querySelectorAll('.filter.active').forEach(f => f.classList.remove('active'));
            filter.classList.add('active');
            currentFilter = filter.textContent.trim();
            applyFiltering();
        });
    });

    applyFiltering();
});
