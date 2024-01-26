from IPython.display import clear_output, display

import requests
from bs4 import BeautifulSoup
import json

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import pandas as pd
pd.set_option('display.max_rows', 1000)
pd.set_option('max_colwidth', 400)
import numpy as np

import json
import time
import mouse
import os
from os.path import exists
import re
from win32api import GetSystemMetrics

from typing import Callable, Union, List
from collections.abc import Iterable



# Калибровка размера экрана для Selenium драйвера
def driver_screen_calibration(x, reverse=False):
    '''
    Корректировка координаты по x для драйвера (У меня почему-то параметры экрана 
    для драйвера отличаются от параметров, которые видит система, поэтому 
    приходится переводить значения для соотносимости с драйвером и наоборот, 
    поэтому если все норм, то в качестве коэффициента для x прописываем 1)
    '''
    # 1596 -- координата крайней правой точкчки по X (где пропадает окно приложения)
    # -7 -- координата крайней левой точкчки по X (где появляется окно приложения)
    
    if not reverse:
        new_x = x * (1596 + 7) / 1920 - 7
    else:
        new_x = (x + 7) * 1920 / (1596 + 7)
        
    return new_x


def search_query(driver, text: str = 'Магнит'):
    '''
    Для ввода поискового запроса в строку поиска
    '''
    input_text_element = driver.find_element(By.XPATH, 
                                             value="//input[@class='input__control _bold']")
    input_text_element.send_keys(Keys.CONTROL + "a");
    input_text_element.send_keys(Keys.DELETE);
    input_text_element.send_keys(text)
    input_text_element.send_keys(Keys.ENTER)
    

def form_geo_data_frame(snippet_elements: list):
    '''
    Парсим сниппеты для нахождения адреса и координат в рамках отображаемого куска карты
    '''
    # Парсим Адреса
    adress = [element.find_element(by=By.CLASS_NAME, 
                                   value='search-business-snippet-view__address')\
                                    .text\
                    for element in snippet_elements]
    # Парсим координаты
    coordinates = [element.find_element(by='xpath', 
                                        value='div')\
                        .get_attribute('data-coordinates').split(',') \
                    for element in snippet_elements]

    # Проверка соответствия длин
    assert len(adress) == len(coordinates), 'Длины списков не совпадают'

    # Формируем ДФ
    geo_df = pd.DataFrame({'adress': adress})
    geo_df[['lat', 'lon']] = coordinates
    
    return geo_df


def mouse_placer_decorator(screen_width):
    def actual_decorator(func):
        def wrapper(*args, **kwargs):
            '''
            Декоратор для приведения мыши к нужной зоне
            '''
            x, y = mouse.get_position()
            mouse.move(screen_width * 0.75, 
                       0, 
                       absolute=True, 
                       duration=0)
            mouse.click()
            # Декорируемая функция
            func(*args, **kwargs)
            mouse.move(x, 
                       y, 
                       absolute=True, 
                       duration=0)

        return wrapper
    return actual_decorator

def decrease_win_scale(iterations: int=5):    
    '''
    Костыль для уменьшения масшатаба окна
    '''
    import keyboard
    
    for i in range(iterations):
        keyboard.press_and_release('ctrl+-')


def get_coordinates(url:str):
    '''
    Экстрактим координаты центра карты из фильтра для адреса страницы
    '''
    if 'https://yandex.ru/map' in url:
        coordinates_pair = re.search(r'[\?&]ll=(.{5,30})&', url)
        coordinates_pair = coordinates_pair.group(1)
        
        return coordinates_pair.split('%2C')
    
    else:
        print('Не тот URL')
        
        
def get_zoom_value(url):
    '''
    Экстрактим значение зума из фильтра для адреса страницы
    '''
    if 'https://yandex.ru/map' in url:
        zoom_value = re.search(r'[\?&]z=(\d{1,3}\.?\d{0,2})', url)
        zoom_value = zoom_value.group(1)
        
        return zoom_value
    
    else:
        print('Не тот URL')


def get_delta_info(driver):
    '''
    Функция для определения 
    '''
    # Определяем координаты центра карты до смещения
    lat_curr, lon_curr = tuple(map(lambda x: float(x), 
                               get_coordinates(driver.current_url)))
    
    # Получаем необходимые параметры элементов страницы
    coords = driver.get_window_position(windowHandle='current')
    sidebar_width = driver.find_element(by=By.CLASS_NAME, 
                                         value='sidebar-view__panel').size['width']
    map_height, map_width = driver.find_element(by=By.CLASS_NAME, 
                               value='map-container').size.values()

    delta_y, delta_x = map(lambda x: driver_screen_calibration(x*0.5*0.5,
                                                               reverse=True)//100*100, 
                           (map_height, map_width))

    # Двигаем мышь на центр объекта карты
    mouse.move(driver_screen_calibration(coords['x'] + (sidebar_width + map_width*0.5)*0.5, 
                                         reverse=True), 
               HEIGHT * 0.5, 
               absolute=True, 
               duration=0)  # Задаем элементы условия для цикла

    driver_screen_calibration(map_width*0.5*0.5, reverse=True)

    # Перетаскиваем на N пикселей
    mouse.hold()
    time.sleep(1)
    mouse.drag(0, 0, 
               -delta_x, delta_y, 
               absolute=False, duration=3.7)
    time.sleep(1)
    
    # Определяем координаты центра карты после смещения
    lat_new, lon_new = tuple(map(lambda x: float(x), 
                           get_coordinates(driver.current_url)))
    
    # Определяем дельту смещения
    lat_delta = (lat_new - lat_curr) * 2
    lon_delta = (lon_new - lon_curr) * 2

    return lat_delta, lon_delta


def replace_filter_value(url:str, 
                         new_value: List[int], 
                         filter_text:str, 
                         get_function: Callable[[str], str]):
    '''
    Для замены значений у фильтров
    '''
    # Проверям входное значение и оборачиваем в список, если не в списке
    if not isinstance(new_value, Iterable):
        new_value = [new_value]
        
    # Парсим текущее значение фильтра
    current_value = get_function(url)
    
    # Оборачиваем в список, если нужно
    if not isinstance(current_value, Iterable)\
        or isinstance(current_value, str):
        current_value = [current_value]
    
    # Замена значений в выбранном фильтре
    new_url = url.replace(filter_text.format(*current_value),
                        filter_text.format(*new_value))
    
    return new_url


def move_to_url(driver,
                lon_lat: List[int], 
                zoom: int=12,
                url_with_filters: str='https://yandex.ru/maps/?ll=50%2C80&z=10'):
    '''
    Переходит по адресу с заданными координатами и значением приближения
    '''
    # Задаются дефолтные значения url и фильтров
    coordinate_filter_text = 'll={}%2C{}'
    zoom_filter_text = 'z={}'
    
    # Подставляем значения широты и долготы 
    start_point_url = replace_filter_value(url=url_with_filters,
                                             new_value=lon_lat,
                                             filter_text=coordinate_filter_text,
                                             get_function=get_coordinates)
    # Подставляем значения зума
    start_point_url = replace_filter_value(url=start_point_url,
                                             new_value=zoom,
                                             filter_text=zoom_filter_text,
                                             get_function=get_zoom_value)
    
    # Возвращаем сформированный адрес
    return start_point_url


def mouse_placer_for_scroler_decorator(func):
    def wrapper(*args, **kwargs):
        '''
        Декоратор для позиционирования курсора для скролинга
        '''
        # Активируем окно и двигаем мышь в нужную область 
        mouse.move(driver_screen_calibration(WIN_POSITION_X + WIN_WIDTH*0.5, 
                                             reverse=True), 
                   0, 
                   absolute=True, 
                   duration=0)
        mouse.click()
        
        return func(*args, **kwargs)
    
    return wrapper


@mouse_placer_for_scroler_decorator
def gather_all_snippets(driver):
    '''
    Автоматизация для прокрутки скроллбара и сбора данных по каждой найденной точке
    '''
    global snippet_elements
    
    # Подготовка элементов для условия цикла
    prev_len = 0
    snippet_elements = driver.find_elements(by=By.CLASS_NAME, 
                                            value='search-snippet-view')
    curr_len = len(snippet_elements)
    # Определяем координаты зоны для скролинга
    coords = driver.get_window_position(windowHandle='current')
    sidebar_length = driver.find_element(by=By.CLASS_NAME, 
                                         value='sidebar-view__panel')\
                            .size['width']

    # Лупим прокрутку до тех пор, пока не перестанут подгружаться новые сниппеты
    while curr_len != prev_len:
        time.sleep(2)
        clear_output()
        print('Количество загруженных точек: ', curr_len)
        # Двигаем мышь на место прокрутки
        mouse.move(driver_screen_calibration(coords['x'] + sidebar_length*0.5*0.5, 
                                             reverse=True), 
                   HEIGHT * 0.5, 
                   absolute=True, 
                   duration=0.1)
        # Прокрутка
        mouse.wheel(delta=-200)
        time.sleep(1)
        # ПроверОчка

        # Луп с проверкой статуса подгрузки новых точек
        counter = 0
        loading = bool(driver.find_elements(by=By.CLASS_NAME, 
                         value='search-list-view__spinner-text'))
        while loading and counter <= 5:
            time.sleep(1)
            counter += 1
            # Статус загрузки
            loading = bool(driver.find_elements(by=By.CLASS_NAME, 
                     value='search-list-view__spinner-text'))

        # Обновляем список элементов
        snippet_elements = driver.find_elements(by=By.CLASS_NAME, 
                                                value='search-snippet-view')
        # Обновляем элементы условия
        prev_len, curr_len = curr_len, len(snippet_elements)

    # Формируем ДФ с адресом и координатами
    geo_df = form_geo_data_frame(snippet_elements)
    
    return geo_df


def zoom_value_calibration(driver, 
                           lon_lat: List[int], 
                           init_zoom: int,
                           brand_name: str='Магнит'):
    '''
    Калибровка для определения оптимального значения зума
    '''
    # Ищем сеть
    search_query(driver=driver, text=brand_name)
    time.sleep(2)

    for zoom_value in range(init_zoom, 16):
        # Переходим по указанным координатам с текущим зумом
        new_url = move_to_url(driver=driver,
                                lon_lat=lon_lat, 
                                zoom=zoom_value,
                                url_with_filters=driver.current_url)
        driver.get(new_url)

        # Создаем список-болванку для фиксации размера датасета
        amount_list = []

        for i in range(2):
            # Собираем данныaе с текущим зумом
            brand_df = gather_all_snippets(driver=driver)

            # Добавляем к списку длину датасета
            amount_list.append(len(brand_df))

            # Обновляем страницу для следующей итерации
            driver.refresh()
            time.sleep(2)

        # Условие для раннего выхода из цикла
        if len(set(amount_list)) == 1:
            break

    print('Рекомендуемое значение зума: ', zoom_value)


def parse_data_within_rect(driver, 
                           topleft_lon_lat: List[int],        # Широта, долгота верхней левой точки 
                           bottomright_lon_lat: List[int],    # Широта, долгота нижней правой точки 
                           delta_coef:float=0.8,
                           zoom:int=12,
                           brand_name: str='Магнит',
                           file_name: str='geo_data.csv'):
    '''
    Итеративно парсим информацию о точках с яндекс карт в рамках указанного прямоугольника
    '''
    # Определяем URL для стартовой точки
    start_point_url = move_to_url(driver=driver, 
                                  lon_lat=topleft_lon_lat)
    # Переходим на стартовую точку
    driver.get(start_point_url)
    # Получаем значения шага по широте и долготе для перехода на новый квадрат
    delta_lon_lat = get_delta_info(driver)
    # Корректировка шага при помощи коэффициента delta_coef
    delta_lon_lat = tuple(map(lambda x: x * delta_coef, delta_lon_lat))

    # Возвращаемся на стартовую точку
    driver.get(start_point_url)

    # Ищем сеть
    search_query(driver=driver, text=brand_name)
    time.sleep(2)
    current_url = driver.current_url

    # Определяем URL для стартовой точки
    start_point_url = move_to_url(driver=driver, 
                                  lon_lat=topleft_lon_lat,
                                  url_with_filters=current_url)
    # Переходим на стартовую точку
    driver.get(start_point_url)

    # Фиксируем исходное значение по долготе
    current_lon_bkp = topleft_lon_lat[0]
    # Распределяем данные из списка
    current_lon, current_lat = topleft_lon_lat
    delta_lon, delta_lat = delta_lon_lat
    finish_lon, finish_lat = bottomright_lon_lat

    # Цикл по широте
    while current_lat > finish_lat - delta_lat:
        current_lon = current_lon_bkp
        # Цикл по долготе
        while current_lon < finish_lon + delta_lon:
            # Переходим на страницу следующего квадрата
            print('Переходим на квадрат с координатами: ', current_lon, current_lat)
            new_url = move_to_url(driver=driver, 
                                    lon_lat=[current_lon, current_lat],
                                    url_with_filters=driver.current_url)
            driver.get(new_url)
            time.sleep(2)
            # Собираем информацию о магазинах с прогруженного квадрата карты
            brand_df = gather_all_snippets(driver)
            brand_df.insert(0, 'brand_name', brand_name)
            # Сохраняем собранные данные
            brand_df.to_csv(file_name, 
                               mode='a' if exists(file_name) else 'w', 
                               sep='\t', 
                               index=False,
                               header = not exists(file_name))



            current_lon += delta_lon 

        current_lat -= delta_lat
        


# Задаем константные параметры
WIDTH = GetSystemMetrics(0)
HEIGHT = GetSystemMetrics(1)
DRIVER_WIDTH = driver_screen_calibration(WIDTH) + 7
DRIVER_HEIGHT = driver_screen_calibration(HEIGHT) + 7

WIN_POSITION_X = driver_screen_calibration(WIDTH * 0.4)
WIN_POSITION_Y = 0

WIN_WIDTH = DRIVER_WIDTH - WIN_POSITION_X
WIN_HEIGHT = DRIVER_HEIGHT * 0.95
