from collections import OrderedDict

from devito.tools import timed_pass
from devito.types import (TimeDimension)
from devito.ir.iet import (Expression, Increment, Iteration, List, Conditional, SyncSpot,
                           Section, HaloSpot, ExpressionBundle)

__all__ = ['iet_build']


@timed_pass(name='build')
def iet_build(stree, **kwargs):
    """
    Construct an Iteration/Expression tree(IET) from a ScheduleTree.
    """
    dswap = kwargs['options']['disk-swap']
    time_iterators = None

    nsections = 0
    queues = OrderedDict()
    for i in stree.visit():
        if i == stree:
            # We hit this handle at the very end of the visit
            iet_body = queues.pop(i)
            if(dswap):
                from devito.passes.iet import disk_swap_build
                iet_body = disk_swap_build(iet_body, dswap, kwargs['sregistry'].nthreads, kwargs['options']['mpi'], kwargs['language'], time_iterators)               
            return List(body=iet_body)

        elif i.is_Exprs:
            exprs = []
            for e in i.exprs:
                if e.is_Increment:
                    exprs.append(Increment(e))
                else:
                    exprs.append(Expression(e, operation=e.operation))
            body = ExpressionBundle(i.ispace, i.ops, i.traffic, body=exprs)

        elif i.is_Conditional:
            body = Conditional(i.guard, queues.pop(i))

        elif i.is_Iteration:
            if i.dim.is_Virtual:
                body = List(body=queues.pop(i))
            else:
                iteration_nodes = queues.pop(i) 
                if isinstance(i.dim, TimeDimension) and dswap and dswap.mode == 'write':
                    if dswap.compression:
                        iteration_nodes.append(Section("compress_temp"))
                    else:
                        iteration_nodes.append(Section("write_temp"))
                    time_iterators = i.sub_iterators
                elif isinstance(i.dim, TimeDimension) and dswap and dswap.mode == 'read':
                    if dswap.compression:
                        iteration_nodes.insert(0, Section("decompress_temp"))
                    else:
                        iteration_nodes.insert(0, Section("read_temp"))
                    time_iterators = i.sub_iterators

                body = Iteration(iteration_nodes, i.dim, i.limits,
                                direction=i.direction, properties=i.properties,
                                uindices=i.sub_iterators)

        elif i.is_Section:
            body = Section('section%d' % nsections, body=queues.pop(i))
            nsections += 1

        elif i.is_Halo:
            try:
                body = HaloSpot(queues.pop(i), i.halo_scheme)
            except KeyError:
                body = HaloSpot(None, i.halo_scheme)

        elif i.is_Sync:
            body = SyncSpot(i.sync_ops, body=queues.pop(i, None))

        queues.setdefault(i.parent, []).append(body)

    assert False
