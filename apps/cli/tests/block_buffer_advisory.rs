//! Reproduce the advisory's post-panic condition on the exact legacy dependency.
//! Each interrupted computation is discarded or reset after checking its cursor.

use block_buffer::{EagerBuffer, LazyBuffer, generic_array::typenum::U4};
use std::panic::{AssertUnwindSafe, catch_unwind};

#[test]
fn legacy_partial_eager_cursor_survives_every_tail_byte_after_callback_panic() {
    for tail in 0..=u8::MAX {
        let mut buffer = EagerBuffer::<U4>::new(&[1, 2]);
        let mut observed = Vec::new();
        let interrupted = catch_unwind(AssertUnwindSafe(|| {
            buffer.digest_blocks(&[3, tail], |blocks| {
                observed = blocks
                    .iter()
                    .map(|block| block.to_vec())
                    .collect::<Vec<_>>();
                panic!("synthetic compression interruption");
            });
        }));
        assert!(interrupted.is_err());
        assert_eq!(observed, [vec![1, 2, 3, tail]]);
        assert_eq!(buffer.get_pos(), 2);
        assert_eq!(buffer.get_data(), [1, 2]);
        buffer.reset();
        buffer.digest_blocks(&[42], |_| panic!("a partial block must not compress"));
        assert_eq!(buffer.get_pos(), 1);
        assert_eq!(buffer.get_data(), [42]);
    }
}

#[test]
fn legacy_full_eager_cursor_survives_callback_panic() {
    let mut buffer = EagerBuffer::<U4>::default();
    let mut observed = Vec::new();
    let interrupted = catch_unwind(AssertUnwindSafe(|| {
        buffer.digest_blocks(&[1, 2, 3, 0xff], |blocks| {
            observed = blocks
                .iter()
                .map(|block| block.to_vec())
                .collect::<Vec<_>>();
            panic!("synthetic compression interruption");
        });
    }));
    assert!(interrupted.is_err());
    assert_eq!(observed, [vec![1, 2, 3, 0xff]]);
    assert_eq!(buffer.get_pos(), 0);
    assert!(buffer.get_data().is_empty());
}

#[test]
fn legacy_generated_data_cannot_overwrite_the_separate_cursor_after_panic() {
    for first in 0..=u8::MAX {
        let mut buffer = EagerBuffer::<U4>::default();
        let mut output = [0; 1];
        let mut callback_reached = false;
        let interrupted = catch_unwind(AssertUnwindSafe(|| {
            buffer.set_data(&mut output, |blocks| {
                if let Some(block) = blocks.first_mut() {
                    block[0] = first;
                    callback_reached = true;
                    panic!("synthetic generation interruption");
                }
            });
        }));
        assert!(interrupted.is_err() && callback_reached);
        assert_eq!(buffer.get_pos(), 0);
        assert!(buffer.get_data().is_empty());
        buffer.reset();
        buffer.set_data(&mut output, |blocks| {
            for block in blocks {
                block.fill(42);
            }
        });
        assert_eq!(output, [42]);
        assert_eq!(buffer.get_pos(), 1);
    }
}

#[test]
fn legacy_lazy_full_cursor_stays_in_bounds_after_callback_panic() {
    let mut buffer = LazyBuffer::<U4>::new(&[1, 2, 3, 4]);
    let mut observed = Vec::new();
    let interrupted = catch_unwind(AssertUnwindSafe(|| {
        buffer.digest_blocks(&[0xff], |blocks| {
            observed = blocks
                .iter()
                .map(|block| block.to_vec())
                .collect::<Vec<_>>();
            panic!("synthetic lazy compression interruption");
        });
    }));
    assert!(interrupted.is_err());
    assert_eq!(observed, [vec![1, 2, 3, 4]]);
    assert_eq!(buffer.get_pos(), 4);
    assert_eq!(buffer.get_data(), [1, 2, 3, 4]);
    buffer.reset();
    buffer.digest_blocks(&[42; 5], |_| {});
    assert_eq!(buffer.get_pos(), 1);
    assert_eq!(buffer.get_data(), [42]);
}
