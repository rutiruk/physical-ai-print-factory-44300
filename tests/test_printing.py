import pytest
from print_factory.printing import FormLot,booklet_forms,gather


def ready(form,copies=100,job='BROCHURE',revision=1):
    lot=FormLot(job,revision,form,copies)
    lot.print_side('front',proof_approved=True,imposition_approved=True)
    lot.print_side('back',proof_approved=True,imposition_approved=True)
    lot.cure();lot.inspect(True);lot.jog();lot.fold()
    return lot


def test_16_page_imposition_produces_four_correct_duplex_forms():
    assert booklet_forms(16)==[((16,1),(2,15)),((14,3),(4,13)),((12,5),(6,11)),((10,7),(8,9))]
    assert sorted(p for sides in booklet_forms(16) for side in sides for p in side)==list(range(1,17))
    with pytest.raises(ValueError):booklet_forms(15)


def test_prepress_approval_is_required_before_printing():
    lot=FormLot('J',1,1,100)
    with pytest.raises(ValueError):lot.print_side('front',proof_approved=False,imposition_approved=True)
    assert not lot.front_printed


@pytest.mark.parametrize('missing',['back','cure','inspection','jog','orientation'])
def test_unready_printed_lot_cannot_enter_folder(missing):
    lot=FormLot('J',1,1,100)
    lot.print_side('front',True,True)
    if missing!='back':lot.print_side('back',True,True)
    if missing not in ('back','cure'):lot.cure()
    if missing!='inspection':lot.inspect(True)
    if missing!='jog':lot.jog()
    if missing=='orientation':lot.head_up=False
    with pytest.raises(ValueError):lot.fold()


def test_rejected_inspection_is_not_allowed_to_fold():
    lot=ready(1);lot.folded=False;lot.inspect(False)
    with pytest.raises(ValueError):lot.fold()


@pytest.mark.parametrize('fault',['missing','duplicate','order','job','revision','quantity','not_folded'])
def test_gather_rejects_bad_forms_without_consuming_any_input(fault):
    lots=[ready(i) for i in [4,3,2,1]]
    if fault=='missing':lots.pop()
    if fault=='duplicate':lots[-1]=ready(2)
    if fault=='order':lots.reverse()
    if fault=='job':lots[0].job='OTHER'
    if fault=='revision':lots[0].revision=2
    if fault=='quantity':lots[0].copies=99
    if fault=='not_folded':lots[0].folded=False
    with pytest.raises(ValueError):gather(lots,'BROCHURE',1)
    assert not any(l.consumed for l in lots)


def test_400_printed_sheets_become_100_booklets_with_conserved_mass():
    lots=[ready(i) for i in [4,3,2,1]]
    source_mass=sum(l.mass_kg for l in lots)
    books=gather(lots,'BROCHURE',1)
    assert books.copies==100 and books.pages==16
    with pytest.raises(ValueError):books.trim()
    books.stitch();books.trim();books.pack()
    assert books.finished_size_m==(.210,.297)
    assert books.packed and all(l.consumed for l in lots)
    assert source_mass==pytest.approx(5.76)
    assert books.product_mass_kg+books.trim_waste_kg==pytest.approx(source_mass)
    assert books.product_mass_kg==pytest.approx(4.9896)
    with pytest.raises(ValueError):gather(lots,'BROCHURE',1)


def test_flat_folded_and_finished_geometry_reflect_real_dimensions():
    lot=FormLot('J',1,1,100)
    assert lot.size_m==pytest.approx((.45,.32,.01))
    lot=ready(1)
    assert lot.size_m==pytest.approx((.225,.32,.02))
    assert lot.mass_kg==pytest.approx(1.44)
def test_four_page_leaflet_bypasses_wire_but_still_requires_finishing():
    import pytest
    from print_factory.printing import FormLot,gather
    lot=FormLot('LEAFLET',1,1,100,pages=4)
    lot.print_side('front',True,True);lot.print_side('back',True,True)
    lot.cure();lot.inspect(True);lot.jog();lot.fold()
    product=gather([lot],'LEAFLET',1)
    assert product.binding=='fold_only'
    with pytest.raises(ValueError):product.stitch()
    with pytest.raises(ValueError):product.pack()
    product.trim();product.pack()
    assert product.packed and not product.stitched

