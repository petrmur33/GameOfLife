import pygame as pg
import pygame.gfxdraw

import itertools
import random
import sys
import time
import multiprocessing
from typing import Callable
from functools import partial


WINDOW_TITLE = "Game Of Life"
PAUSED_FPS = 10

class RenderWorker(multiprocessing.Process):
    def __init__(self, task_queue: multiprocessing.JoinableQueue, result_queue: multiprocessing.Queue):
        self.task_queue = task_queue
        self.result_queue = result_queue
        super().__init__()

    
    def run(self):
        while True:
            task = self.task_queue.get()
            if task is None:
                self.task_queue.task_done()
                break
            result = task()
            self.result_queue.put(result, block=False)
            self.task_queue.task_done()


class App:
    def __init__(self, resolution: tuple[int, int] = (800, 600), field_size: tuple[int, int] = (80, 60), fps: int = 75, cores: int = 1, performance_mode: bool = False):

        self.performance_mode = performance_mode
        self.resolution = resolution
        
        self.target_fps = fps
        self.paused_fps = 10
        self.current_fps = self.paused_fps
        
        self.field_width, self.field_height = field_size
        self._random_generate_field()
        self.zero_field = list(list(0 for _ in range(self.field_width)) for _ in range(self.field_height))
        
        self.cores = cores
        self._multiprocessing_init()

        if not pg.get_init():
            pg.init()

        if not pg.font.get_init():
            pg.font.init()

        self.game_tickrate_clock = pg.time.Clock()

        self.screen = pg.display.set_mode(self.resolution)
        pg.display.set_caption(WINDOW_TITLE)
        self.debug_font = pg.font.SysFont("Consolas", 20)

        self.paused = True


    def _multiprocessing_init(self) -> None:
        multiprocessing.freeze_support()
        self.worker_zero_field = list(list(0 for _ in range(self.field_width)) for _ in range((self.field_height - 2) // self.cores))
        self.render_workers = []
        self.task_queue = multiprocessing.JoinableQueue()
        self.result_queue = multiprocessing.Queue()
        for _ in range(self.cores):
            render_worker = RenderWorker(self.task_queue, self.result_queue)
            self.render_workers.append(render_worker)
            render_worker.start()


    def _random_generate_field(self):
        self._generate_field_by_rule(lambda : random.randint(0, 1))


    # TODO: Call rule with x, y arguments
    def _generate_field_by_rule(self, rule: Callable):
        self.field = list(list(rule() for _ in range(self.field_width)) for _ in range(self.field_height))
        self.generation_counter = 0


    @staticmethod
    def _next_generation_in_center(field: list[list[bool]], field_width: int, field_height: int, offset_x: int, offset_y: int, zero_field: list[list[0]]) -> list[list[bool]]:
        """
        field arg including near cells. \n
        field_width and field_height indicates field arg size. \n
        offsets necessary only for mark where is work done (offsets only used in return statement). \n
        zero field (field_width-2 * filed_height-2) necessary for instant usage.
        """
        new_field = zero_field
        # time1 = time.perf_counter_ns()
        for y, x in itertools.product(range(1, field_height - 1), range(1, field_width - 1)):
            # time3 = time.perf_counter_ns()
            alives = sum(field[dy][dx] for dy, dx in itertools.product(range(y - 1, y + 2), range(x - 1, x + 2))) - field[y][x]
            # time4 = time.perf_counter_ns()
            # print(f"alives_calculations: {time4 - time3}")

            # time3 = time.perf_counter_ns()
            if field[y][x] and (alives < 2 or alives > 3):
                new_field[y-1][x-1] = 0
            elif not field[y][x] and alives == 3:
                new_field[y-1][x-1] = 1
            else:
                new_field[y-1][x-1] = field[y][x]
            # time4 = time.perf_counter_ns()
            # print(f"if_statement: {time4 - time3}")
        # time2 = time.perf_counter_ns()
        # print(f"for_loop: {time2 - time1}")
        return offset_x, offset_y, new_field


    def _next_generation_start(self):
        self.next_field = self.zero_field

        part_height = (self.field_height - 2) // self.cores
        for i in range(self.cores):
            offset_x = 1
            offset_y = i * part_height + 1
            field = self.field[i * part_height:(i+1) * part_height + 2]
            task = partial(self._next_generation_in_center, field, self.field_width, len(field), offset_x, offset_y, self.worker_zero_field)
            self.task_queue.put(task)

    
    def _build_next_generation(self):
        # Corners
        for y, x in itertools.product((0, self.field_height - 1), (0, self.field_width - 1)):
            alives = 0
            dy_min = y - 1 if y != 0 else y
            dy_max = y + 2 if y != self.field_height - 1 else y + 1
            dx_min = x - 1 if x != 0 else x
            dx_max = x + 2 if x != self.field_width - 1 else x + 1
            alives = sum(self.field[dy][dx] for dy, dx in itertools.product(range(dy_min, dy_max), range(dx_min, dx_max))) - self.field[y][x]

            if self.field[y][x] and (alives < 2 or alives > 3):
                self.next_field[y][x] = 0
            elif not self.field[y][x] and alives == 3:
                self.next_field[y][x] = 1
            else:
                self.next_field[y][x] = self.field[y][x]

        # Left side
        # x = 0
        dx_min = 0
        dx_max = 2 if self.field_width - 1 != 0 else 1
        for y in range(1, self.field_height - 1):
            alives = 0
            dy_min = y - 1 if y != 0 else y
            dy_max = y + 2 if y != self.field_height - 1 else y + 1
            alives = sum(self.field[dy][dx] for dy, dx in itertools.product(range(dy_min, dy_max), range(dx_min, dx_max))) - self.field[y][0]

            if self.field[y][0] and (alives < 2 or alives > 3):
                self.next_field[y][0] = 0
            elif not self.field[y][0] and alives == 3:
                self.next_field[y][0] = 1
            else:
                self.next_field[y][0] = self.field[y][0]

        # Right side
        # x = self.field_width - 1
        dx_min = self.field_width - 2 if self.field_width - 1 != 0 else self.field_width - 1
        dx_max = self.field_width
        for y in range(1, self.field_height - 1):
            alives = 0
            dy_min = y - 1 if y != 0 else y
            dy_max = y + 2 if y != self.field_height - 1 else y + 1
            alives = sum(self.field[dy][dx] for dy, dx in itertools.product(range(dy_min, dy_max), range(dx_min, dx_max))) - self.field[y][self.field_width - 1]

            if self.field[y][self.field_width - 1] and (alives < 2 or alives > 3):
                self.next_field[y][self.field_width - 1] = 0
            elif not self.field[y][self.field_width - 1] and alives == 3:
                self.next_field[y][self.field_width - 1] = 1
            else:
                self.next_field[y][self.field_width - 1] = self.field[y][self.field_width - 1]

        # TODO: Make top side and bottom side in one loop
        # Top side
        # y = 0
        dy_min = 0
        dy_max = 2 if self.field_height - 1 != 0 else 1
        for x in range(1, self.field_width - 1):
            alives = 0   # TODO: why is alives = 0
            dx_min = x - 1 if x != 0 else x
            dx_max = x + 2 if x != self.field_width - 1 else x + 1
            alives = sum(self.field[dy][dx] for dy, dx in itertools.product(range(dy_min, dy_max), range(dx_min, dx_max))) - self.field[0][x]

            if self.field[0][x] and (alives < 2 or alives > 3):
                self.next_field[0][x] = 0
            elif not self.field[0][x] and alives == 3:
                self.next_field[0][x] = 1
            else:
                self.next_field[0][x] = self.field[0][x]
        
        # Bottom side
        # y = self.field_height - 1
        dy_min = self.field_height - 2 if self.field_height - 1 != 0 else self.field_height - 1
        dy_max = self.field_height
        for x in range(1, self.field_width - 1):
            alives = 0
            dx_min = x - 1 if x != 0 else x
            dx_max = x + 2 if x != self.field_width - 1 else x + 1
            alives = sum(self.field[dy][dx] for dy, dx in itertools.product(range(dy_min, dy_max), range(dx_min, dx_max))) - self.field[self.field_height - 1][x]

            if self.field[self.field_height - 1][x] and (alives < 2 or alives > 3):
                self.next_field[self.field_height - 1][x] = 0
            elif not self.field[self.field_height - 1][x] and alives == 3:
                self.next_field[self.field_height - 1][x] = 1
            else:
                self.next_field[self.field_height - 1][x] = self.field[self.field_height - 1][x]
        
        # time1 = time.perf_counter_ns()
        for _ in range(self.cores):
            offset_x, offset_y, result_field = self.result_queue.get()
            for y, row in enumerate(result_field):
                self.next_field[y+offset_y] = [self.next_field[y+offset_y][0]] + row + [self.next_field[y+offset_y][-1]]
        # time2 = time.perf_counter_ns()
        # print(f"building_field: {time2 - time1}")
            
        self.task_queue.join()

        self.field = self.next_field
        self.generation_counter += 1


    def run(self):
        if self.performance_mode:
            while True:
                total_time1 = time.perf_counter_ns()

                time1 = time.perf_counter_ns()
                self.event()
                time2 = time.perf_counter_ns()
                print(f"event: {time2 - time1}")

                time1 = time.perf_counter_ns()
                self.keys()
                time2 = time.perf_counter_ns()
                print(f"keys: {time2 - time1}")
    
                time1 = time.perf_counter_ns()
                self.mouse()
                time2 = time.perf_counter_ns()
                print(f"mouse: {time2 - time1}")
    
                if not self.paused:
                    time1 = time.perf_counter_ns()
                    self._next_generation_start()
                    time2 = time.perf_counter_ns()
                    print(f"_next_generation_start: {time2 - time1}")
    
                    time1 = time.perf_counter_ns()
                    self.render()
                    time2 = time.perf_counter_ns()
                    print(f"render: {time2 - time1}")
    
                    time1 = time.perf_counter_ns()
                    self._build_next_generation()
                    time2 = time.perf_counter_ns()
                    print(f"_build_next_generation: {time2 - time1}")

                total_time2 = time.perf_counter_ns()
                print(f"Total time elapsed: {total_time2 - total_time1}ns\n\n")
        else:
            while True:
                self.event()
                self.keys()
                self.mouse()
                if not self.paused:
                    self._next_generation_start()
                    self.render()
                    self._build_next_generation()
                self.tick()


    def mouse(self):
        keys = pg.mouse.get_pressed()


    def render(self):
        cell_width = self.resolution[0] // self.field_width
        cell_height = self.resolution[1] // self.field_height

        # Field render
        # part_height = self.field_height // self.cores
        # for i in range(self.cores):
        #     offset_x = 0
        #     offset_y = i * cell_height * part_height
        #     field = self.field[i * part_height:(i+1) * part_height]
        #     task = partial(self._render_field, self.screen, offset_x, offset_y, cell_width, cell_height, field)
        #     self.task_queue.put(task)
        # self.task_queue.join()
        
        self.screen.fill((0, 0, 0))
        for y, row in enumerate(self.field):
            for x, cell in enumerate(row):
                if cell:
                    pygame.gfxdraw.box(self.screen, pg.Rect(x*cell_width, y*cell_height, cell_width, cell_height), (255, 255, 255))

        # PAUSED text render
        if self.paused:
            self.screen.blit(self.debug_font.render("PAUSED", True, (255, 0, 0)), (0, 0))

        # FPS render
        self.screen.blit(self.debug_font.render(f"{int(self.game_tickrate_clock.get_fps())} FPS", True, (0, 255, 0)), (self.resolution[0] - 100, 0))

        # Generation render counter
        self.screen.blit(self.debug_font.render(f"{self.generation_counter}", True, (0, 255, 0)), (0, self.resolution[1] - 21))

        pg.display.flip()


    def keys(self):
        keys = pg.key.get_pressed()
        

    def event(self):
        events = pg.event.get()
        for event in events:
            if event.type == pg.QUIT:
                self.exit()
            if event.type == pg.MOUSEBUTTONDOWN:
                mouse_x, mouse_y = pg.mouse.get_pos()
                y = mouse_y // (self.resolution[1] // self.field_height)
                x = mouse_x // (self.resolution[0] // self.field_width)
                self.field[y][x] = 0 if self.field[y][x] == 1 else 1
                self.render()
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_SPACE:
                    self.paused = not self.paused
                    self.current_fps = self.paused_fps if self.paused else self.target_fps
                    self.render()
                if event.key == pg.K_r:
                    self._random_generate_field()
                    self.render()
                if event.key == pg.K_c:
                    self._generate_field_by_rule(int)
                    self.render()
                if event.key == pg.K_F11:
                    pg.display.toggle_fullscreen()
                if event.key == pg.K_ESCAPE:
                    self.exit()


    def tick(self):
        self.game_tickrate_clock.tick(self.current_fps)


    def exit(self, code: int = 0):
        # Closing processes
        for _ in range(self.cores):
            self.task_queue.put(None)
        self.task_queue.join()
        self.task_queue.close()

        sys.exit(code)


def main(args):
    app = App(resolution=(1280, 720), field_size=(160, 90), fps=1000, performance_mode=False, cores=12)
    app.run()


if __name__ == "__main__":
    main(sys.argv)
