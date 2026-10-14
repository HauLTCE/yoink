import { b } from './b';
import { x } from './x';
import _ from 'lodash';

export function a(): number {
    _.noop();
    return b() + x();
}
