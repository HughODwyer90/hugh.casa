document.addEventListener('DOMContentLoaded', () => {
    let currentFilter = 'All';

    function sortTable(tableId, columnIndex) {
        const table = document.getElementById(tableId);
        if (!table) return; // Prevent errors if table isn't found

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

    function filterTable() {
        const query = document.getElementById('searchBox').value.toLowerCase();
        const entityTable = document.getElementById('entitiesTable');
        const integrationTable = document.getElementById('integrationsTable');

        // Apply filtering to entities table (if it exists)
        if (entityTable) {
            entityTable.querySelectorAll('tbody tr').forEach(row => {
                const entityId = row.cells[0].textContent.trim().toLowerCase();
                const matchesFilter = currentFilter === 'All' || entityId.startsWith(currentFilter.toLowerCase());
                const matchesQuery = Array.from(row.cells).some(cell => cell.textContent.toLowerCase().includes(query));
                row.style.display = matchesFilter && matchesQuery ? '' : 'none';
            });
        }

        // Apply filtering to integrations table (if it exists)
        if (integrationTable) {
            integrationTable.querySelectorAll('tbody tr').forEach(row => {
                const integrationId = row.cells[0].textContent.trim().toLowerCase();
                const matchesFilter = currentFilter === 'All' || integrationId.startsWith(currentFilter.toLowerCase());
                const matchesQuery = Array.from(row.cells).some(cell => cell.textContent.toLowerCase().includes(query));
                row.style.display = matchesFilter && matchesQuery ? '' : 'none';
            });
        }
    }

    document.getElementById('searchBox').addEventListener('input', filterTable);

    document.querySelectorAll('.filter').forEach(filter => {
        filter.addEventListener('click', () => {
            document.querySelectorAll('.filter.active').forEach(f => f.classList.remove('active'));
            filter.classList.add('active');
            currentFilter = filter.textContent.trim();
            filterTable();
        });
    });

    filterTable();
});
