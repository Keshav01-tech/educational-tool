package controllers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/keshav/bookstore/package/models"
	"github.com/keshav/bookstore/package/utils"
)

var NewBook models.Book

// CREATE
func CreateBook(c *gin.Context) {
	utils.ParseBody(c.Request, &NewBook)

	book := NewBook.CreateBook()
	c.JSON(http.StatusOK, book)

}

// GET ALL
func GetBooks(c *gin.Context) {
	books := models.GetAllBooks()

	c.JSON(http.StatusOK, books)
}

// GET BY ID
func BookByID(c *gin.Context) {
	id := c.Param("id")
	ID, _ := strconv.ParseInt(id, 0, 64)

	book, _ := models.GetBookById(ID)

	c.JSON(http.StatusOK, book)
}

func Delete(c *gin.Context) {
	id := c.Param("id")
	ID, _ := strconv.ParseInt(id, 0, 64)

	book := models.DeleteBook(ID)

	c.JSON(http.StatusOK, book)
}

func Update(c *gin.Context) {
	var updateBook models.Book

	utils.ParseBody(c.Request, &updateBook)

	id := c.Param("id")
	ID, _ := strconv.ParseInt(id, 0, 64)

	book, db := models.GetBookById(ID)

	if db.Error != nil {
		c.JSON(http.StatusNotFound, gin.H{"message": "book not found"})
		return
	}

	if updateBook.Name != "" {
		book.Name = updateBook.Name
	}
	if updateBook.Author != "" {
		book.Author = updateBook.Author
	}
	if updateBook.Publication != "" {
		book.Publication = updateBook.Publication
	}
    
	models.DB.Save(&book)
	

	c.JSON(http.StatusOK, book)
}
