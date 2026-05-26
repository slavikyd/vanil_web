# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
import uuid

from django.db import models
from django.utils import timezone


class YoyoLog(models.Model):
    id = models.CharField(primary_key=True, max_length=36)
    migration_hash = models.CharField(max_length=64, blank=True, null=True)
    migration_id = models.CharField(max_length=255, blank=True, null=True)
    operation = models.CharField(max_length=10, blank=True, null=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    hostname = models.CharField(max_length=255, blank=True, null=True)
    comment = models.CharField(max_length=255, blank=True, null=True)
    created_at_utc = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = '_yoyo_log'


class YoyoMigration(models.Model):
    migration_hash = models.CharField(primary_key=True, max_length=64)
    migration_id = models.CharField(max_length=255, blank=True, null=True)
    applied_at_utc = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = '_yoyo_migration'


class YoyoVersion(models.Model):
    version = models.IntegerField(primary_key=True)
    installed_at_utc = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = '_yoyo_version'


class Cashiers(models.Model):
    id = models.TextField(primary_key=True, default=uuid.uuid4)
    full_name = models.TextField(max_length=100)
    is_admin = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name

    class Meta:
        managed = True
        db_table = 'cashiers'
        verbose_name = 'Кассир'
        verbose_name_plural = 'Кассиры'


class Categories(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.TextField(unique=True)


    def __str__(self):
        return self.name
    
    
    class Meta:
        managed = True
        db_table = 'categories'
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'


class Items(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.TextField(max_length=100)
    active = models.BooleanField()
    category = models.ForeignKey(Categories, models.DO_NOTHING, db_column='category', blank=True, null=True)
    tbl = models.IntegerField(null=True, blank=True)
    pos = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        managed = True
        db_table = 'items'
        verbose_name = 'Позиция'
        verbose_name_plural = 'Позиции'


class Orders(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created = models.DateTimeField(default=timezone.now)
    shop = models.ForeignKey('Shops', models.DO_NOTHING, blank=True, null=True)
    cashier = models.ForeignKey(Cashiers, models.DO_NOTHING, blank=True, null=True)
    address = models.TextField()
    order_for = models.DateField()
    comment = models.TextField(null=True, blank=True, max_length=255)
    disabled = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)

    class Meta:
        managed = True
        db_table = 'orders'
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'


class OrdersItems(models.Model):
    pk = models.CompositePrimaryKey("order_id", "item_id")
    order = models.ForeignKey(Orders, models.DO_NOTHING)
    item = models.ForeignKey(Items, models.DO_NOTHING)
    quantity = models.IntegerField(blank=True, null=True)
    comment = models.TextField(null=True, blank=True, max_length=100)
    order_type = models.TextField(default='Обычный')


    class Meta:
        managed = True
        db_table = 'orders_items'
        verbose_name = 'Товар к заказу'
        verbose_name_plural = 'Товары к заказам'

class ShopsGroups(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.TextField(max_length=100)

    def __str__(self):
        return self.name or str(self.id)

    class Meta:
        managed = True
        db_table = 'shops_groups'
        verbose_name = 'Группа магазинов'
        verbose_name_plural = 'Группы магазинов'

class Shops(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    phone_number = models.TextField()
    address = models.TextField(max_length=255)
    shop_group = models.ForeignKey(ShopsGroups, models.DO_NOTHING, blank=True, null=True, db_column='shop_group')
    android_id = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.address
    

    class Meta:
        managed = True
        db_table = 'shops'
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'


class ShopsOrders(models.Model):
    pk = models.CompositePrimaryKey("shop_id", "order_id")
    shop = models.ForeignKey(Shops, models.DO_NOTHING)
    order = models.ForeignKey(Orders, models.DO_NOTHING)

    class Meta:
        managed = True
        db_table = 'shops_orders'



class YoyoLock(models.Model):
    locked = models.IntegerField(primary_key=True)
    ctime = models.DateTimeField(blank=True, null=True)
    pid = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'yoyo_lock'

