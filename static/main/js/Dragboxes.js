/// <reference path="typescript-declarations.d.ts" />
// Code for supporting drag-select
var Dragboxes;
(function (Dragboxes) {
    'use strict';
    var globalChecked = null;
    function findAndInitAllTables() {
        $('table.dragboxes').each(function (i, table) { return initTable(table); });
    }
    Dragboxes.findAndInitAllTables = findAndInitAllTables;
    function dragEnd(event) {
        globalChecked = null;
        event.data.table.off('mouseover.dragboxes');
    }
    Dragboxes.dragEnd = dragEnd;
    function dragOver(event) {
        if (globalChecked !== null) {
            $(':checkbox', this).prop('checked', globalChecked).trigger('change');
        }
    }
    Dragboxes.dragOver = dragOver;
    function dragStart(event) {
        var $this = $(this), checkbox, table;
        // ignore mouse events not using the left mouse button
        if (event.which !== 1) {
            return true;
        }
        // mousedown toggles the clicked checkbox value and stores new value in globalChecked
        if (globalChecked === null) {
            // may have clicked label, so go to parent TD and find the checkbox
            checkbox = $this.closest('td').find(':checkbox');
            // have to check for null to prevent double event from clicking label
            checkbox.prop('checked', function (i, value) {
                return (globalChecked = !value);
            }).trigger('change');
        }
        // also attaches mouseover event to all cells in parent table
        table = $this.closest('.dragboxes').on('mouseover.dragboxes', 'td', dragOver);
        // wait for mouse to go up anywhere, then end drag events
        $(document).one('mouseup.dragboxes', { 'table': table }, dragEnd);
        return false;
    }
    Dragboxes.dragStart = dragStart;
    function initTable(table) {
        $(table).filter('.dragboxes')
            .on('mousedown.dragboxes', 'td :checkbox', dragStart)
            .on('mousedown.dragboxes', 'td label', dragStart)
            .on('click.dragboxes', 'td :checkbox', function () { return false; });
    }
    Dragboxes.initTable = initTable;
})(Dragboxes || (Dragboxes = {}));
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiRHJhZ2JveGVzLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiRHJhZ2JveGVzLnRzIl0sIm5hbWVzIjpbIkRyYWdib3hlcyIsIkRyYWdib3hlcy5maW5kQW5kSW5pdEFsbFRhYmxlcyIsIkRyYWdib3hlcy5kcmFnRW5kIiwiRHJhZ2JveGVzLmRyYWdPdmVyIiwiRHJhZ2JveGVzLmRyYWdTdGFydCIsIkRyYWdib3hlcy5pbml0VGFibGUiXSwibWFwcGluZ3MiOiJBQUFBLHFEQUFxRDtBQUVyRCxrQ0FBa0M7QUFFbEMsSUFBTyxTQUFTLENBbURmO0FBbkRELFdBQU8sU0FBUyxFQUFDLENBQUM7SUFDZEEsWUFBWUEsQ0FBQ0E7SUFFYkEsSUFBSUEsYUFBYUEsR0FBV0EsSUFBSUEsQ0FBQ0E7SUFFcENBO1FBQ0NDLENBQUNBLENBQUNBLGlCQUFpQkEsQ0FBQ0EsQ0FBQ0EsSUFBSUEsQ0FBQ0EsVUFBQ0EsQ0FBUUEsRUFBRUEsS0FBaUJBLElBQVVBLE9BQUFBLFNBQVNBLENBQUNBLEtBQUtBLENBQUNBLEVBQWhCQSxDQUFnQkEsQ0FBQ0EsQ0FBQ0E7SUFDbkZBLENBQUNBO0lBRmVELDhCQUFvQkEsdUJBRW5DQSxDQUFBQTtJQUVFQSxpQkFBd0JBLEtBQTRCQTtRQUNoREUsYUFBYUEsR0FBR0EsSUFBSUEsQ0FBQ0E7UUFDckJBLEtBQUtBLENBQUNBLElBQUlBLENBQUNBLEtBQUtBLENBQUNBLEdBQUdBLENBQUNBLHFCQUFxQkEsQ0FBQ0EsQ0FBQ0E7SUFDaERBLENBQUNBO0lBSGVGLGlCQUFPQSxVQUd0QkEsQ0FBQUE7SUFFREEsa0JBQXlCQSxLQUE0QkE7UUFDakRHLEVBQUVBLENBQUNBLENBQUNBLGFBQWFBLEtBQUtBLElBQUlBLENBQUNBLENBQUNBLENBQUNBO1lBQ3pCQSxDQUFDQSxDQUFDQSxXQUFXQSxFQUFFQSxJQUFJQSxDQUFDQSxDQUFDQSxJQUFJQSxDQUFDQSxTQUFTQSxFQUFFQSxhQUFhQSxDQUFDQSxDQUFDQSxPQUFPQSxDQUFDQSxRQUFRQSxDQUFDQSxDQUFDQTtRQUMxRUEsQ0FBQ0E7SUFDTEEsQ0FBQ0E7SUFKZUgsa0JBQVFBLFdBSXZCQSxDQUFBQTtJQUVEQSxtQkFBMEJBLEtBQTRCQTtRQUNsREksSUFBSUEsS0FBS0EsR0FBVUEsQ0FBQ0EsQ0FBQ0EsSUFBSUEsQ0FBQ0EsRUFBRUEsUUFBZ0JBLEVBQUVBLEtBQVlBLENBQUNBO1FBQzNEQSxzREFBc0RBO1FBQ3REQSxFQUFFQSxDQUFDQSxDQUFDQSxLQUFLQSxDQUFDQSxLQUFLQSxLQUFLQSxDQUFDQSxDQUFDQSxDQUFDQSxDQUFDQTtZQUNwQkEsTUFBTUEsQ0FBQ0EsSUFBSUEsQ0FBQ0E7UUFDaEJBLENBQUNBO1FBQ0RBLHFGQUFxRkE7UUFDckZBLEVBQUVBLENBQUNBLENBQUNBLGFBQWFBLEtBQUtBLElBQUlBLENBQUNBLENBQUNBLENBQUNBO1lBQ3pCQSxtRUFBbUVBO1lBQ25FQSxRQUFRQSxHQUFHQSxLQUFLQSxDQUFDQSxPQUFPQSxDQUFDQSxJQUFJQSxDQUFDQSxDQUFDQSxJQUFJQSxDQUFDQSxXQUFXQSxDQUFDQSxDQUFDQTtZQUNqREEscUVBQXFFQTtZQUNyRUEsUUFBUUEsQ0FBQ0EsSUFBSUEsQ0FBQ0EsU0FBU0EsRUFBRUEsVUFBQ0EsQ0FBUUEsRUFBRUEsS0FBYUE7Z0JBQzdDQSxNQUFNQSxDQUFDQSxDQUFDQSxhQUFhQSxHQUFHQSxDQUFDQSxLQUFLQSxDQUFDQSxDQUFDQTtZQUNwQ0EsQ0FBQ0EsQ0FBQ0EsQ0FBQ0EsT0FBT0EsQ0FBQ0EsUUFBUUEsQ0FBQ0EsQ0FBQ0E7UUFDekJBLENBQUNBO1FBQ0RBLDZEQUE2REE7UUFDN0RBLEtBQUtBLEdBQUdBLEtBQUtBLENBQUNBLE9BQU9BLENBQUNBLFlBQVlBLENBQUNBLENBQUNBLEVBQUVBLENBQUNBLHFCQUFxQkEsRUFBRUEsSUFBSUEsRUFBRUEsUUFBUUEsQ0FBQ0EsQ0FBQ0E7UUFDOUVBLHlEQUF5REE7UUFDekRBLENBQUNBLENBQUNBLFFBQVFBLENBQUNBLENBQUNBLEdBQUdBLENBQUNBLG1CQUFtQkEsRUFBRUEsRUFBRUEsT0FBT0EsRUFBRUEsS0FBS0EsRUFBRUEsRUFBRUEsT0FBT0EsQ0FBQ0EsQ0FBQ0E7UUFDbEVBLE1BQU1BLENBQUNBLEtBQUtBLENBQUNBO0lBQ2pCQSxDQUFDQTtJQXBCZUosbUJBQVNBLFlBb0J4QkEsQ0FBQUE7SUFFREEsbUJBQTBCQSxLQUEyQkE7UUFDakRLLENBQUNBLENBQUNBLEtBQUtBLENBQUNBLENBQUNBLE1BQU1BLENBQUNBLFlBQVlBLENBQUNBO2FBRXhCQSxFQUFFQSxDQUFDQSxxQkFBcUJBLEVBQUVBLGNBQWNBLEVBQUVBLFNBQVNBLENBQUNBO2FBRXBEQSxFQUFFQSxDQUFDQSxxQkFBcUJBLEVBQUVBLFVBQVVBLEVBQUVBLFNBQVNBLENBQUNBO2FBRWhEQSxFQUFFQSxDQUFDQSxpQkFBaUJBLEVBQUVBLGNBQWNBLEVBQUVBLGNBQWNBLE9BQUFBLEtBQUtBLEVBQUxBLENBQUtBLENBQUNBLENBQUNBO0lBQ3BFQSxDQUFDQTtJQVJlTCxtQkFBU0EsWUFReEJBLENBQUFBO0FBQ0xBLENBQUNBLEVBbkRNLFNBQVMsS0FBVCxTQUFTLFFBbURmIiwic291cmNlc0NvbnRlbnQiOlsiLy8vIDxyZWZlcmVuY2UgcGF0aD1cInR5cGVzY3JpcHQtZGVjbGFyYXRpb25zLmQudHNcIiAvPlxuXG4vLyBDb2RlIGZvciBzdXBwb3J0aW5nIGRyYWctc2VsZWN0XG5cbm1vZHVsZSBEcmFnYm94ZXMge1xuICAgICd1c2Ugc3RyaWN0JztcblxuICAgIHZhciBnbG9iYWxDaGVja2VkOmJvb2xlYW4gPSBudWxsO1xuXG5cdGV4cG9ydCBmdW5jdGlvbiBmaW5kQW5kSW5pdEFsbFRhYmxlcygpOnZvaWQge1xuXHRcdCQoJ3RhYmxlLmRyYWdib3hlcycpLmVhY2goKGk6bnVtYmVyLCB0YWJsZTpIVE1MRWxlbWVudCk6dm9pZCA9PiBpbml0VGFibGUodGFibGUpKTtcblx0fVxuXG4gICAgZXhwb3J0IGZ1bmN0aW9uIGRyYWdFbmQoZXZlbnQ6SlF1ZXJ5TW91c2VFdmVudE9iamVjdCk6dm9pZCB7XG4gICAgICAgIGdsb2JhbENoZWNrZWQgPSBudWxsO1xuICAgICAgICBldmVudC5kYXRhLnRhYmxlLm9mZignbW91c2VvdmVyLmRyYWdib3hlcycpO1xuICAgIH1cblxuICAgIGV4cG9ydCBmdW5jdGlvbiBkcmFnT3ZlcihldmVudDpKUXVlcnlNb3VzZUV2ZW50T2JqZWN0KTp2b2lkIHtcbiAgICAgICAgaWYgKGdsb2JhbENoZWNrZWQgIT09IG51bGwpIHtcbiAgICAgICAgICAgICQoJzpjaGVja2JveCcsIHRoaXMpLnByb3AoJ2NoZWNrZWQnLCBnbG9iYWxDaGVja2VkKS50cmlnZ2VyKCdjaGFuZ2UnKTtcbiAgICAgICAgfVxuICAgIH1cblxuICAgIGV4cG9ydCBmdW5jdGlvbiBkcmFnU3RhcnQoZXZlbnQ6SlF1ZXJ5TW91c2VFdmVudE9iamVjdCk6Ym9vbGVhbiB7XG4gICAgICAgIHZhciAkdGhpczpKUXVlcnkgPSAkKHRoaXMpLCBjaGVja2JveDogSlF1ZXJ5LCB0YWJsZTpKUXVlcnk7XG4gICAgICAgIC8vIGlnbm9yZSBtb3VzZSBldmVudHMgbm90IHVzaW5nIHRoZSBsZWZ0IG1vdXNlIGJ1dHRvblxuICAgICAgICBpZiAoZXZlbnQud2hpY2ggIT09IDEpIHtcbiAgICAgICAgICAgIHJldHVybiB0cnVlO1xuICAgICAgICB9XG4gICAgICAgIC8vIG1vdXNlZG93biB0b2dnbGVzIHRoZSBjbGlja2VkIGNoZWNrYm94IHZhbHVlIGFuZCBzdG9yZXMgbmV3IHZhbHVlIGluIGdsb2JhbENoZWNrZWRcbiAgICAgICAgaWYgKGdsb2JhbENoZWNrZWQgPT09IG51bGwpIHtcbiAgICAgICAgICAgIC8vIG1heSBoYXZlIGNsaWNrZWQgbGFiZWwsIHNvIGdvIHRvIHBhcmVudCBURCBhbmQgZmluZCB0aGUgY2hlY2tib3hcbiAgICAgICAgICAgIGNoZWNrYm94ID0gJHRoaXMuY2xvc2VzdCgndGQnKS5maW5kKCc6Y2hlY2tib3gnKTtcbiAgICAgICAgICAgIC8vIGhhdmUgdG8gY2hlY2sgZm9yIG51bGwgdG8gcHJldmVudCBkb3VibGUgZXZlbnQgZnJvbSBjbGlja2luZyBsYWJlbFxuICAgICAgICAgICAgY2hlY2tib3gucHJvcCgnY2hlY2tlZCcsIChpOm51bWJlciwgdmFsdWU6Ym9vbGVhbik6Ym9vbGVhbiA9PiB7XG4gICAgICAgICAgICAgICAgcmV0dXJuIChnbG9iYWxDaGVja2VkID0gIXZhbHVlKTtcbiAgICAgICAgICAgIH0pLnRyaWdnZXIoJ2NoYW5nZScpO1xuICAgICAgICB9XG4gICAgICAgIC8vIGFsc28gYXR0YWNoZXMgbW91c2VvdmVyIGV2ZW50IHRvIGFsbCBjZWxscyBpbiBwYXJlbnQgdGFibGVcbiAgICAgICAgdGFibGUgPSAkdGhpcy5jbG9zZXN0KCcuZHJhZ2JveGVzJykub24oJ21vdXNlb3Zlci5kcmFnYm94ZXMnLCAndGQnLCBkcmFnT3Zlcik7XG4gICAgICAgIC8vIHdhaXQgZm9yIG1vdXNlIHRvIGdvIHVwIGFueXdoZXJlLCB0aGVuIGVuZCBkcmFnIGV2ZW50c1xuICAgICAgICAkKGRvY3VtZW50KS5vbmUoJ21vdXNldXAuZHJhZ2JveGVzJywgeyAndGFibGUnOiB0YWJsZSB9LCBkcmFnRW5kKTtcbiAgICAgICAgcmV0dXJuIGZhbHNlO1xuICAgIH1cblxuICAgIGV4cG9ydCBmdW5jdGlvbiBpbml0VGFibGUodGFibGU6IEpRdWVyeSB8IEhUTUxFbGVtZW50KTp2b2lkIHtcbiAgICAgICAgJCh0YWJsZSkuZmlsdGVyKCcuZHJhZ2JveGVzJylcbiAgICAgICAgICAgIC8vIHdhdGNoIGZvciBtb3VzZWRvd24gb24gY2hlY2tib3hlc1xuICAgICAgICAgICAgLm9uKCdtb3VzZWRvd24uZHJhZ2JveGVzJywgJ3RkIDpjaGVja2JveCcsIGRyYWdTdGFydClcbiAgICAgICAgICAgIC8vIGFsc28gd2F0Y2ggZm9yIG1vdXNlZG93biBvbiBsYWJlbHNcbiAgICAgICAgICAgIC5vbignbW91c2Vkb3duLmRyYWdib3hlcycsICd0ZCBsYWJlbCcsIGRyYWdTdGFydClcbiAgICAgICAgICAgIC8vIGRpc2FibGUgY2xpY2sgYmVjYXVzZSBtb3VzZWRvd24gaXMgaGFuZGxpbmcgaXQgbm93XG4gICAgICAgICAgICAub24oJ2NsaWNrLmRyYWdib3hlcycsICd0ZCA6Y2hlY2tib3gnLCAoKTpib29sZWFuID0+IGZhbHNlKTtcbiAgICB9XG59XG4iXX0=